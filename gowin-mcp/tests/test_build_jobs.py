"""Persistent build ownership and evidence tests; fake processes are not EDA proof."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

import test_server as baseline_tests

server = baseline_tests.server


class BuildJobsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Match _prepare_build's resolved paths, including Windows 8.3 temp aliases.
        self.root = Path(self.temp.name).resolve()
        self.project = baseline_tests.GowinMcpTests().write_project(self.root, [("top.v", "file.verilog")])
        (self.root / "top.v").write_text("module top; endmodule", encoding="ascii")
        self.env = patch.dict(os.environ, {"GOWIN_ALLOWED_ROOTS": str(self.root)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.prepare = patch.object(server, "_prepare_build", return_value=(self.project, Path("fake-gw-sh.exe"), "fixed Tcl"))
        self.prepare.start()
        self.addCleanup(self.prepare.stop)

    def start(self, stage="all"):
        with patch.object(server.subprocess, "Popen"):
            return server.gowin_start_build(str(self.project), stage, 30)

    def run_worker(self, job, text="[100%] Power analysis completed\n", artifact=True, code=0, mutate=False,
                   outputs=None):
        class FakeTool:
            pid = 42

            def __init__(inner, command, **kwargs):
                kwargs["stdout"].write(text.encode())
                if artifact:
                    names = outputs if outputs is not None else (
                        "demo.fs", "demo.p", "demo.pr", "demo_tr_content.html", "demo.pin.html")
                    for name in names:
                        destination = self.root / "impl" / "pnr" / name
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_text("fake stage output", encoding="ascii")
                if mutate:
                    (self.root / "top.v").write_text("module changed; endmodule", encoding="ascii")

            def wait(inner, timeout):
                return code

            def poll(inner):
                return code

        with patch.object(server.subprocess, "Popen", FakeTool):
            server._build_worker(str(self.project), job["build_id"])
        return server.gowin_build_status(str(self.project), job["build_id"])

    def test_async_start_blocks_duplicate_and_returns_without_waiting(self):
        job = self.start()
        self.assertEqual(job["state"], "starting")
        self.assertFalse(job["success"])
        with self.assertRaisesRegex(RuntimeError, "owns this project"):
            self.start()

    def test_receipt_survives_new_server_and_stale_heartbeat_is_unknown(self):
        job = self.start()
        receipt_path = Path(job["receipt_path"])
        receipt = json.loads(receipt_path.read_text())
        receipt.update(heartbeat_epoch=time.time() - 60, started_epoch=time.time() - 90)
        receipt_path.write_text(json.dumps(receipt))
        # Separate interpreter: no in-memory job registry is needed.
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "gowin_build_status", "arguments": {"project_file": str(self.project), "build_id": job["build_id"]}}}
        completed = subprocess.run([os.sys.executable, str(Path(server.__file__))], input=json.dumps(request)+"\n",
                                   text=True, capture_output=True, check=True)
        result = json.loads(json.loads(completed.stdout)["result"]["content"][0]["text"])
        self.assertEqual(result["state"], "unknown")
        self.assertTrue(result["budget_exceeded"])
        self.assertTrue((self.root / ".gowin-mcp/build.lock").exists())

    def test_success_needs_new_artifact_and_records_hash(self):
        result = self.run_worker(self.start())
        self.assertTrue(result["success"])
        self.assertEqual(result["evidence_level"], "bitstream-generated")
        self.assertTrue(result["requires_report_review"])
        self.assertEqual(len(result["new_bitstreams"][0]["sha256"]), 64)
        self.assertFalse((self.root / ".gowin-mcp/build.lock").exists())
        (self.root / "top.v").write_text("module later; endmodule")
        changed = server.gowin_build_status(str(self.project), result["build_id"])
        self.assertFalse(changed["success"])
        self.assertEqual(changed["evidence_level"], "stale-build")

    def test_zero_exit_does_not_hide_error_or_stale_artifact(self):
        result = self.run_worker(self.start(), text="ERROR (PR1234) : failed\n")
        self.assertFalse(result["success"])
        destination = self.root / "impl/pnr/demo.fs"
        os.utime(destination, (1, 1))
        result = self.run_worker(self.start(), artifact=False)
        self.assertFalse(result["success"])
        self.assertEqual(result["new_bitstreams"], [])

    def test_source_change_during_build_rejects_delivery(self):
        result = self.run_worker(self.start(), mutate=True)
        self.assertFalse(result["success"])
        self.assertFalse(result["inputs_unchanged"])

    def test_overwritten_output_invalidates_old_receipt(self):
        result = self.run_worker(self.start())
        (self.root / "impl/pnr/demo.fs").write_text("different bitstream")
        result = server.gowin_build_status(str(self.project), result["build_id"])
        self.assertFalse(result["success"])
        self.assertFalse(result["artifacts_match_now"])

    def test_failed_worker_launch_releases_its_lock(self):
        with patch.object(server.subprocess, "Popen", side_effect=OSError("launch failed")):
            with self.assertRaisesRegex(OSError, "launch failed"):
                server.gowin_start_build(str(self.project))
        self.assertFalse((self.root / ".gowin-mcp/build.lock").exists())

    def test_synthesis_requires_fresh_report(self):
        result = self.run_worker(self.start("syn"), artifact=False)
        self.assertFalse(result["success"])
        self.assertEqual(result["missing_outputs"], ["synthesis"])

    def test_placement_and_zero_unrouted_do_not_prove_route_completion(self):
        result = self.run_worker(self.start(), outputs=["demo.p", "demo.pin.html"], text=(
            "Running routing......\n[90%] Routing Phase 3 completed\n"
            "ERROR (PR0004) : There are total 0 unrouted nets\n"
            'Generate file "demo.pin.html" completed\n'))
        self.assertFalse(result["success"])
        self.assertEqual(result["log"]["unrouted_nets"], 0)
        self.assertEqual(result["log"]["error_count"], 1)
        self.assertEqual(result["log"]["last_stage"]["name"], "routing")
        self.assertEqual(result["missing_outputs"], ["route", "timing", "bitstream"])
        self.assertEqual(result["stage_outputs"]["placement"], [str(Path("impl/pnr/demo.p"))])

    def test_partial_stale_and_empty_outputs_are_not_accepted(self):
        for missing in ("demo.pr", "demo_tr_content.html", "demo.pin.html", "demo.fs"):
            with self.subTest(missing=missing):
                # A previous build's file may still exist in impl/.
                destination = self.root / "impl/pnr" / missing
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text("old output")
                os.utime(destination, (1, 1))
                outputs = [name for name in ("demo.pr", "demo_tr_content.html", "demo.pin.html", "demo.fs")
                           if name != missing]
                result = self.run_worker(self.start(), outputs=outputs)
                self.assertFalse(result["success"])
                self.assertEqual(len(result["missing_outputs"]), 1)
        job = self.start()
        (self.root / "impl/pnr/demo.fs").write_bytes(b"")
        result = self.run_worker(job, outputs=["demo.pr", "demo_tr_content.html", "demo.pin.html"])
        self.assertFalse(result["success"])
        self.assertEqual(result["new_bitstreams"], [])
        self.assertEqual(result["missing_outputs"], ["bitstream"])

    def test_artifact_inventory_is_complete_but_binaries_are_not_archived(self):
        job = self.start()
        result = self.run_worker(job, outputs=["demo.fs", "demo.p", "demo.pr", "demo_tr_content.html",
                                                "demo.pin.html", *[f"extra{i}.log" for i in range(110)]])
        self.assertTrue(result["success"])
        self.assertEqual(len(result["new_artifacts"]), 115)
        self.assertEqual(len(result["new_bitstreams"]), 1)
        archive = Path(result["report_archive"]) / "impl/pnr"
        self.assertFalse((archive / "demo.pr").exists())
        self.assertFalse((archive / "demo.p").exists())
        self.assertTrue((archive / "demo_tr_content.html").exists())

    def test_log_stage_is_literal_and_absent_unrouted_count_is_unknown(self):
        log = self.root / "build.log"
        for line, stage in (("Running placement......", "placement"),
                            ("[80%] Routing Phase 2 completed", "routing"),
                            ("Running timing analysis......", "timing"),
                            ("Bitstream generation completed", "bitstream"),
                            ("Running power analysis......", "power")):
            with self.subTest(stage=stage):
                log.write_text(line + '\nGenerate file "demo.rpt.txt" completed\n')
                result = server.gowin_diagnose_log(str(self.project))
                self.assertEqual(result["last_stage"], {"name": stage, "line": 1, "text": line})
                self.assertIsNone(result["unrouted_nets"])
        log.write_text("ERROR (PR0004) : There are total 119 unrouted nets\n")
        result = server.gowin_diagnose_log(str(self.project))
        self.assertEqual(result["unrouted_nets"], 119)
        self.assertEqual(result["unrouted_evidence"]["line"], 1)

    def test_log_counts_are_not_truncated_and_first_error_is_retained(self):
        log = self.root / "build.log"
        log.write_text("WARN (NL0002) : unused\n" * 120 + "ERROR (PR1) : root cause\n[70%] Routing Phase 1 completed\n")
        result = server.gowin_diagnose_log(str(self.project), max_messages=2)
        self.assertEqual(result["warning_count"], 120)
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(result["first_error"]["line"], 121)
        self.assertTrue(result["messages_truncated"])
        self.assertIn("70%", result["last_progress"]["text"])
        self.assertEqual(result["process_state"], "not-probed")

    def test_paths_and_ids_stay_scoped(self):
        with self.assertRaises(PermissionError):
            server.gowin_diagnose_log(str(self.project), "../outside.log")
        with self.assertRaises(ValueError):
            server.gowin_build_status(str(self.project), "../other")
        with self.assertRaises(ValueError):
            server._tcl_path(Path("C:/unsafe{path}/demo.gprj"))

    def start_with_options(self, **options):
        with patch.object(server.subprocess, "Popen"):
            return server.gowin_start_build(str(self.project), "pnr", 30, **options)

    def write_cmd_do(self, place, route):
        command_file = self.root / "impl" / "pnr" / "cmd.do"
        command_file.parent.mkdir(parents=True, exist_ok=True)
        command_file.write_text(f"-bit\n-place_option {place}\n-route_option {route}\n-route_maxfan 23\n", encoding="ascii")

    def test_options_are_bounded_integers_and_not_for_synthesis(self):
        for bad in ({"place_option": 5}, {"route_option": 3}, {"place_option": -1},
                    {"place_option": "3; exec calc"}, {"route_option": True}):
            with self.assertRaises(ValueError):
                self.start_with_options(**bad)
        with patch.object(server.subprocess, "Popen"), self.assertRaisesRegex(ValueError, "not syn"):
            server.gowin_start_build(str(self.project), "syn", 30, place_option=3)
        self.assertFalse((self.root / ".gowin-mcp/build.lock").exists())

    def test_requested_options_must_match_what_the_tool_recorded(self):
        job = self.start_with_options(place_option=3, route_option=2)
        self.assertEqual(job["options"], {"place_option": 3, "route_option": 2})
        self.write_cmd_do(0, 2)
        result = self.run_worker(job)
        self.assertFalse(result["success"])
        self.assertFalse(result["options_applied"])
        self.assertEqual(result["applied_options"], {"place_option": 0, "route_option": 2})
        self.write_cmd_do(3, 2)
        result = self.run_worker(self.start_with_options(place_option=3, route_option=2))
        self.assertTrue(result["success"])
        self.assertTrue(result["options_applied"])

    def test_reports_are_archived_per_build_and_survive_the_next_run(self):
        report = self.root / "impl" / "pnr" / "demo.tr.html"
        first = self.start()
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("first timing", encoding="ascii")
        first = self.run_worker(first)
        second = self.start()
        report.write_text("second timing", encoding="ascii")
        second = self.run_worker(second, text="ERROR (PR0004) : There are total 104 unrouted nets\n")
        self.assertFalse(second["success"])
        archived = lambda job: (Path(job["report_archive"]) / "impl/pnr/demo.tr.html").read_text(encoding="ascii")
        self.assertEqual(archived(first), "first timing")
        self.assertEqual(archived(second), "second timing")
        self.assertFalse((Path(first["report_archive"]) / "impl/pnr/demo.fs").exists())

    def test_wait_timeout_does_not_kill_or_restart_build(self):
        job = {"build_id": "a" * 32, "state": "running", "success": False}
        with patch.object(server, "gowin_start_build", return_value=job) as start, \
             patch.object(server.time, "monotonic", side_effect=[0, 31]), \
             patch.object(server.subprocess, "Popen") as popen:
            result = server.gowin_build_project(str(self.project), timeout_seconds=30)
        self.assertTrue(result["wait_timed_out"])
        self.assertEqual(result["state"], "running")
        start.assert_called_once()
        popen.assert_not_called()


class TimingClusterTests(unittest.TestCase):
    PATH = ("<h3>Path{n}</h3><table><tr><td>Slack</td><td>{slack}</td></tr><tr><td>From</td><td>{source}</td></tr>"
            "<tr><td>To</td><td>{target}</td></tr></table><p>Path Statistics:</p><table><tr><td>Logic Level</td>"
            "<td>{levels}</td></tr><tr><td>Arrival Data Path Delay</td><td>cell: 3.0, 20.0%; route: 12.0, {route}%; "
            "tC2Q: 0.3, 2.0%</td></tr></table>")

    def test_setup_paths_group_by_register_bank_and_ignore_hold(self):
        rows = [(-0.092, "u_c/setting_mode_s2/Q", "u_p/voice_stealing_18_s1", 13, 80.0),
                (-0.050, "u_c/setting_mode_s2/Q", "u_p/voice_stealing_3_s1", 12, 70.0),
                (0.300, "u_p/phase[7]_2_s0", "u_p/bank[24].active_s0", 8, 60.0)]
        body = "".join(self.PATH.format(n=i, slack=s, source=a, target=b, levels=l, route=r)
                       for i, (s, a, b, l, r) in enumerate(rows, 1))
        hold = self.PATH.format(n=1, slack=-9.0, source="u_h/a_s0", target="u_h/b_s0", levels=1, route=40.0)
        with tempfile.TemporaryDirectory() as name:
            report = Path(name) / "demo_tr_content.html"
            report.write_text(f"<h3>Setup Analysis Report</h3>{body}<h3>Hold Analysis Report</h3>{hold}", encoding="utf-8")
            clusters = server._setup_clusters(report)
        self.assertEqual(clusters, [
            {"from": "u_c/setting_mode", "to": "u_p/voice_stealing", "paths": 2, "violating_paths": 2,
             "worst_slack_ns": -0.092, "max_logic_levels": 13, "mean_route_delay_percent": 75.0},
            {"from": "u_p/phase[*]", "to": "u_p/bank[*].active", "paths": 1, "violating_paths": 0,
             "worst_slack_ns": 0.3, "max_logic_levels": 8, "mean_route_delay_percent": 60.0}])


class BuildScriptTests(unittest.TestCase):
    def test_options_reach_the_fixed_tcl_before_run(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            project = baseline_tests.GowinMcpTests().write_project(root, [("top.v", "file.verilog")])
            (root / "top.v").write_text("module top; endmodule", encoding="ascii")
            (root / "IDE" / "bin").mkdir(parents=True)
            (root / "IDE" / "bin" / "gw_sh.exe").write_bytes(b"")
            with patch.dict(os.environ, {"GOWIN_ALLOWED_ROOTS": str(root)}), \
                 patch.object(server, "_gowin_home", return_value=root):
                _, _, plain = server._prepare_build(str(project), "pnr")
                _, _, tuned = server._prepare_build(str(project), "pnr", {"route_option": 2, "place_option": 3})
        self.assertNotIn("set_option", plain)
        self.assertIn("    set_option -place_option 3\n    set_option -route_option 2\n    run pnr\n", tuned)


if __name__ == "__main__":
    unittest.main()
