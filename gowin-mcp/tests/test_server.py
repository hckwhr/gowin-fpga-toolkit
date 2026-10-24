from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER_PATH = Path(__file__).parents[1] / "server.py"
SPEC = importlib.util.spec_from_file_location("gowin_mcp_server", SERVER_PATH)
server = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(server)


class GowinMcpTests(unittest.TestCase):
    PART_NUMBER = "GW5AST-LV138PG484AC1/I0"

    def write_project(self, root: Path, files: list[tuple[str, str]]) -> Path:
        entries = []
        for relative, file_type in files:
            entries.append(f'<File path="{relative}" type="{file_type}" enable="1"/>')
        project = root / "demo.gprj"
        project.write_text(
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<Project><Template>FPGA</Template><Version>5</Version>"
            f'<Device name="GW5AST-138C" pn="{self.PART_NUMBER}">device-id</Device>'
            f"<FileList>{''.join(entries)}</FileList></Project>\n",
            encoding="utf-8",
        )
        return project

    def write_timing_report(self, root: Path) -> Path:
        report = root / "impl" / "pnr" / "demo_tr_content.html"
        report.parent.mkdir(parents=True)
        report.write_text(
            textwrap.dedent(
                """
                <html><body>
                <h2>STA Tool Run Summary:</h2><table>
                <tr><td>Setup Delay Model</td><td>Slow</td></tr>
                <tr><td>Hold Delay Model</td><td>Fast</td></tr>
                <tr><td>Numbers of Paths Analyzed</td><td>20</td></tr>
                <tr><td>Numbers of Endpoints Analyzed</td><td>12</td></tr>
                <tr><td>Numbers of Setup Violated Endpoints</td><td>0</td></tr>
                <tr><td>Numbers of Hold Violated Endpoints</td><td>0</td></tr></table>
                <h2>Clock Summary:</h2><table>
                <tr><th>NO.</th><th>Clock Name</th><th>Type</th><th>Period</th><th>Frequency(MHz)</th><th>Rise</th><th>Fall</th><th>Source</th><th>Master</th><th>Objects</th></tr>
                <tr><td>1</td><td>clk</td><td>Base</td><td>20.000</td><td>50.000<td>0</td><td>10</td><td></td><td></td><td>clk</td></tr>
                <tr><td>2</td><td>fabric_clk</td><td>Base</td><td>10.000</td><td>100.000</td><td>0</td><td>5</td><td></td><td></td><td>fabric_clk/Q</td></tr></table>
                <h2>Max Frequency Summary:</h2><table>
                <tr><th>NO.</th><th>Clock Name</th><th>Constraint</th><th>Actual Fmax</th><th>Logic Level</th><th>Entity</th></tr>
                <tr><td>1</td><td>clk</td><td>50.000(MHz)</td><td>125.000(MHz)</td><td>4</td><td>TOP</td></tr></table>
                <h2>Total Negative Slack Summary:</h2><table>
                <tr><th>Clock Name</th><th>Analysis Type</th><th>Endpoints TNS</th><th>Number of Endpoints</th></tr>
                <tr><td>clk</td><td>Setup</td><td>0.000</td><td>0</td></tr>
                <tr><td>clk</td><td>Hold</td><td>0.000</td><td>0</td></tr></table>
                <h3>Setup Paths Table</h3>
                <h4>Report Command:report_timing -setup -max_paths 25 -max_common_paths 1</h4><table>
                <tr><th>Path Number</th><th>Path Slack</th><th>From Node</th><th>To Node</th><th>From Clock</th><th>To Clock</th><th>Relation</th><th>Clock Skew</th><th>Data Delay</th></tr>
                <tr><td>1</td><td>1.250</td><td>a/Q</td><td>b/D</td><td>clk</td><td>clk</td><td>20</td><td>0.1</td><td>18</td></tr></table>
                <h3>Hold Paths Table</h3>
                <h4>Report Command:report_timing -hold -max_paths 25 -max_common_paths 1</h4><table>
                <tr><th>Path Number</th><th>Path Slack</th><th>From Node</th><th>To Node</th><th>From Clock</th><th>To Clock</th><th>Relation</th><th>Clock Skew</th><th>Data Delay</th></tr>
                <tr><td>1</td><td>0.200</td><td>a/Q</td><td>b/D</td><td>clk</td><td>clk</td><td>0</td><td>0</td><td>0.2</td></tr></table>
                <h2>Timing Constraints Report:</h2><table>
                <tr><th>SDC Command Type</th><th>State</th><th>Detail Command</th></tr>
                <tr><td>TC_CLOCK</td><td>Actived</td><td>create_clock -name clk -period 20 [get_ports {clk}]</td></tr></table>
                </body></html>
                """
            ).strip(),
            encoding="utf-8",
        )
        return report

    def test_inspect_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "top.v").write_text("module top; endmodule\n", encoding="ascii")
            project = root / "demo.gprj"
            project.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<Project><Template>FPGA</Template><Version>5</Version>
<Device name="GW5AST-138C" pn="GW5AST-LV138PG484AC1/I0">device-id</Device>
<FileList><File path="top.v" type="file.verilog" enable="1"/>
<File path="missing.cst" type="file.cst" enable="1"/></FileList></Project>
""",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"GOWIN_ALLOWED_ROOTS": str(root)}):
                result = server.gowin_inspect_project(str(project))
            self.assertEqual(result["part_number"], "GW5AST-LV138PG484AC1/I0")
            self.assertEqual(result["missing_files"], ["missing.cst"])

    def test_project_scope_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as allowed, tempfile.TemporaryDirectory() as outside:
            project = Path(outside) / "outside.gprj"
            project.write_text("<Project />", encoding="ascii")
            with patch.dict(os.environ, {"GOWIN_ALLOWED_ROOTS": allowed}):
                with self.assertRaises(PermissionError):
                    server.gowin_inspect_project(str(project))

    def test_timing_summary_parses_reports_and_flags_clock_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "top.v").write_text("module top; endmodule\n", encoding="ascii")
            (root / "demo.sdc").write_text(
                "create_clock -name clk -period 20 [get_ports {clk}]\n", encoding="ascii"
            )
            project = self.write_project(root, [("top.v", "file.verilog"), ("demo.sdc", "file.sdc")])
            report = self.write_timing_report(root)
            wrapper = report.with_name("demo.tr.html")
            wrapper.write_text("<html><body>report frameset</body></html>", encoding="ascii")
            with patch.dict(os.environ, {"GOWIN_ALLOWED_ROOTS": str(root)}):
                result = server.gowin_timing_summary(str(project), max_paths=1)
            self.assertEqual(result["report_path"], str(report))
            self.assertEqual(result["status"], "met-with-coverage-gaps")
            self.assertTrue(result["timing_constraints_met"])
            self.assertFalse(result["timing_clean"])
            self.assertEqual(result["worst_setup_slack_ns"], 1.25)
            self.assertEqual(result["max_frequency"][0]["actual_fmax_mhz"], 125.0)
            self.assertEqual(result["clocks_without_explicit_sdc"], ["fabric_clk"])

    def test_partial_timing_report_never_defaults_missing_data_to_a_pass(self) -> None:
        for removed, expected in (
            ("Numbers of Hold Violated Endpoints", "hold_violated_endpoints"),
            ("Numbers of Setup Violated Endpoints", "setup_violated_endpoints"),
            ("Numbers of Paths Analyzed", "paths_analyzed"),
            ("Numbers of Endpoints Analyzed", "endpoints_analyzed"),
        ):
            with self.subTest(removed=removed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                project = self.write_project(root, [])
                report = self.write_timing_report(root)
                lines = report.read_text().splitlines()
                # The final summary row shares a closing table tag.
                body = "\n".join(lines)
                body = re.sub(r"<tr><td>" + removed + r"</td><td>[^<]*</td></tr>", "", body)
                report.write_text(body)
                with patch.dict(os.environ, {"GOWIN_ALLOWED_ROOTS": str(root)}):
                    result = server.gowin_timing_summary(str(project))
                self.assertEqual(result["status"], "incomplete")
                self.assertFalse(result["timing_clean"])
                self.assertFalse(result["timing_constraints_met"])
                self.assertIn(expected, result["missing_timing_data"])
                self.assertIsNone(result["sta"][expected])

    def test_missing_slack_and_clock_period_block_timing_acceptance(self) -> None:
        for old, new, expected in (
            ("<td>1.250</td>", "<td>N/A</td>", "worst_setup_slack_ns"),
            ("<td>0.200</td>", "<td>N/A</td>", "worst_hold_slack_ns"),
            ("<td>20.000</td>", "<td>N/A</td>", "clock_periods"),
        ):
            with self.subTest(field=expected), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                project = self.write_project(root, [])
                report = self.write_timing_report(root)
                report.write_text(report.read_text().replace(old, new))
                with patch.dict(os.environ, {"GOWIN_ALLOWED_ROOTS": str(root)}):
                    result = server.gowin_timing_summary(str(project))
                self.assertEqual(result["status"], "incomplete")
                self.assertFalse(result["timing_constraints_met"])
                self.assertIn(expected, result["missing_timing_data"])

    def test_pin_audit_finds_duplicates_auto_assignment_and_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cst = root / "demo.cst"
            cst.write_text(
                'IO_LOC "clk" Y18;\n'
                'IO_PORT "clk" IO_TYPE=LVCMOS33 BANK_VCCIO=3.3;\n'
                'IO_LOC "led" Y18;\n'
                'IO_PORT "led" IO_TYPE=LVCMOS33 BANK_VCCIO=3.3;\n',
                encoding="ascii",
            )
            project = self.write_project(root, [("demo.cst", "file.cst")])
            report = root / "impl" / "pnr" / "demo.pin.html"
            report.parent.mkdir(parents=True)
            report.write_text(
                textwrap.dedent(
                    f"""
                    <h1>Pin Messages</h1><table>
                    <tr><td>Part Number</td><td>{self.PART_NUMBER}</td></tr></table>
                    <h2>Pinout by Port Name:</h2><table>
                    <tr><td>Port Name</td><td>Diff Pair</td><td>Loc./Bank</td><td>Constraint</td><td>Dir.</td><td>Site</td><td>CFG</td><td>IO Type</td><td>Drive</td><td>Pull Mode</td><td>BankVccio</td></tr>
                    <tr><td>clk</td><td>-</td><td>Y18/4</td><td>Y</td><td>in</td><td>IOB</td><td>CLK</td><td>LVCMOS33</td><td>OFF</td><td>NONE</td><td>3.3</td></tr>
                    <tr><td>led</td><td>-</td><td>M21/4</td><td>N</td><td>out</td><td>IOB</td><td></td><td>LVCMOS33</td><td>8</td><td>NONE</td><td>3.3</td></tr>
                    </table>
                    """
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"GOWIN_ALLOWED_ROOTS": str(root)}):
                result = server.gowin_pin_audit(str(project), expected_ports=["clk", "led", "rst_n"])
            self.assertEqual(result["duplicate_pins"], [{"pin": "Y18", "ports": ["clk", "led"]}])
            self.assertEqual(result["auto_assigned_ports"], ["led"])
            self.assertEqual(result["expected_ports_without_location"], ["rst_n"])
            self.assertEqual(result["location_mismatches"][0]["port"], "led")
            self.assertFalse(result["clean"])

    def test_pin_audit_marks_incomplete_final_evidence_unclean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cst = root / "demo.cst"
            cst.write_text(
                'IO_LOC "clk" Y18;\n'
                'IO_LOC "orphan" M20;\n'
                'IO_PORT "orphan" IO_TYPE=LVCMOS33 BANK_VCCIO=3.3;\n',
                encoding="ascii",
            )
            project = self.write_project(root, [("demo.cst", "file.cst")])
            with patch.dict(os.environ, {"GOWIN_ALLOWED_ROOTS": str(root)}):
                missing_report = server.gowin_pin_audit(str(project))
            self.assertFalse(missing_report["clean"])
            self.assertIn("final Pin Report is missing", missing_report["issues"])

            report = root / "impl" / "pnr" / "demo.pin.html"
            report.parent.mkdir(parents=True)
            report.write_text(
                textwrap.dedent(
                    f"""
                    <h1>Pin Messages</h1><table>
                    <tr><td>Part Number</td><td>{self.PART_NUMBER}</td></tr></table>
                    <h2>Pinout by Port Name:</h2><table>
                    <tr><td>Port Name</td><td>Diff Pair</td><td>Loc./Bank</td><td>Constraint</td><td>Dir.</td><td>Site</td><td>CFG</td><td>IO Type</td><td>Drive</td><td>Pull Mode</td><td>BankVccio</td></tr>
                    <tr><td>clk</td><td>-</td><td>Y18/4</td><td>Y</td><td>in</td><td>IOB</td><td>CLK</td><td>LVCMOS33</td><td>OFF</td><td>NONE</td><td>3.3</td></tr>
                    <tr><td>led</td><td>-</td><td>M21/4</td><td>N</td><td>out</td><td>IOB</td><td></td><td>LVCMOS33</td><td>8</td><td>NONE</td><td>3.3</td></tr>
                    </table>
                    """
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"GOWIN_ALLOWED_ROOTS": str(root)}):
                result = server.gowin_pin_audit(str(project))
            self.assertEqual(result["ports_without_io_attributes"], ["clk"])
            self.assertEqual(result["final_ports_without_cst"], ["led"])
            self.assertEqual(result["cst_ports_missing_from_final"], ["orphan"])
            self.assertEqual(result["auto_assigned_ports"], ["led"])
            self.assertIn("CST ports are missing IO_PORT attributes", result["issues"])
            self.assertIn("final Pin Report contains ports without CST locations", result["issues"])
            self.assertIn("CST ports are missing from the final Pin Report", result["issues"])
            self.assertIn("final Pin Report contains auto-assigned ports", result["issues"])
            self.assertFalse(result["clean"])

    def test_pin_plan_preview_and_atomic_apply(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cst = root / "demo.cst"
            original = (
                '// board constraints\n'
                'IO_LOC "clk" B2;  // oscillator\n'
                'IO_PORT "clk" IO_TYPE=LVCMOS33 BANK_VCCIO=3.3;\n'
                'IO_LOC "keep" E5;\n'
                'IO_PORT "keep" IO_TYPE=LVCMOS33 BANK_VCCIO=3.3;\n'
            )
            cst.write_text(original, encoding="ascii")
            project = self.write_project(root, [("demo.cst", "file.cst")])
            profile = root / "board.json"
            profile.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "board": "Test Board",
                        "revision": "1.0",
                        "device_name": "GW5AST-138C",
                        "part_number": self.PART_NUMBER,
                        "evidence": ["schematic-test.pdf"],
                        "default_attributes": {"IO_TYPE": "LVCMOS33", "BANK_VCCIO": "3.3"},
                        "pins": [
                            {"pin": "A1", "signal": "clk_50m", "roles": ["clock"], "priority": 0},
                            {"pin": "B2", "signal": "header_1", "roles": ["gpio"], "priority": 2},
                            {"pin": "C3", "signal": "header_2", "roles": ["gpio"], "priority": 1},
                            {"pin": "D4", "signal": "reserved", "roles": ["gpio"], "reserved": True},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            requests = [
                {"port": "clk", "signal": "clk_50m", "role": "clock"},
                {"port": "led", "role": "gpio", "attributes": {"DRIVE": "8", "PULL_MODE": "NONE"}},
            ]
            with patch.dict(os.environ, {"GOWIN_ALLOWED_ROOTS": str(root)}):
                plan = server.gowin_plan_pins(str(project), str(profile), requests)
                self.assertEqual([item["pin"] for item in plan["assignments"]], ["A1", "C3"])
                preview = server.gowin_apply_pin_plan(
                    str(project), str(profile), requests, plan["plan_id"], apply=False
                )
                self.assertFalse(preview["applied"])
                self.assertIn('IO_LOC "clk" A1;', preview["diff"])
                with self.assertRaisesRegex(ValueError, "pin plan changed"):
                    server.gowin_apply_pin_plan(str(project), str(profile), requests, "0" * 64, apply=True)
                applied = server.gowin_apply_pin_plan(
                    str(project), str(profile), requests, plan["plan_id"], apply=True
                )
            self.assertTrue(applied["applied"])
            self.assertTrue(Path(applied["backup_path"]).is_file())
            self.assertEqual(Path(applied["backup_path"]).read_text(encoding="ascii"), original)
            updated = cst.read_text(encoding="ascii")
            self.assertIn('IO_LOC "clk" A1;  // oscillator', updated)
            self.assertIn('IO_LOC "led" C3;', updated)
            self.assertIn('IO_PORT "led" IO_TYPE=LVCMOS33 PULL_MODE=NONE DRIVE=8 BANK_VCCIO=3.3;', updated)
            self.assertIn('IO_LOC "keep" E5;', updated)

    def test_pin_plan_rejects_part_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "demo.cst").write_text("", encoding="ascii")
            project = self.write_project(root, [("demo.cst", "file.cst")])
            profile = root / "board.json"
            profile.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "board": "Wrong Board",
                        "revision": "1.0",
                        "device_name": "GW5AST-138C",
                        "part_number": "GW1N-LV9QN88C6/I5",
                        "evidence": ["schematic.pdf"],
                        "pins": [{"pin": "1", "roles": ["gpio"]}],
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"GOWIN_ALLOWED_ROOTS": str(root)}):
                with self.assertRaisesRegex(ValueError, "does not match project"):
                    server.gowin_plan_pins(str(project), str(profile), [{"port": "led"}])

    def test_pin_plan_rejects_device_name_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "demo.cst").write_text("", encoding="ascii")
            project = self.write_project(root, [("demo.cst", "file.cst")])
            profile = root / "board.json"
            profile.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "board": "Wrong Silicon Revision",
                        "revision": "1.0",
                        "device_name": "GW5AST-138B",
                        "part_number": self.PART_NUMBER,
                        "evidence": ["schematic.pdf"],
                        "default_attributes": {"IO_TYPE": "LVCMOS33", "BANK_VCCIO": "3.3"},
                        "pins": [{"pin": "A1", "roles": ["gpio"]}],
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"GOWIN_ALLOWED_ROOTS": str(root)}):
                with self.assertRaisesRegex(ValueError, "device_name GW5AST-138B"):
                    server.gowin_plan_pins(str(project), str(profile), [{"port": "led"}])

    def test_pin_plan_blocks_apply_without_exact_device_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "demo.cst").write_text("", encoding="ascii")
            project = self.write_project(root, [("demo.cst", "file.cst")])
            profile = root / "board.json"
            profile.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "board": "Legacy Board",
                        "revision": "1.0",
                        "part_number": self.PART_NUMBER,
                        "evidence": ["schematic.pdf"],
                        "default_attributes": {"IO_TYPE": "LVCMOS33", "BANK_VCCIO": "3.3"},
                        "pins": [{"pin": "A1", "roles": ["gpio"]}],
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"GOWIN_ALLOWED_ROOTS": str(root)}):
                plan = server.gowin_plan_pins(str(project), str(profile), [{"port": "led"}])
            self.assertFalse(plan["apply_ready"])
            self.assertIn("exact project device_name", plan["blocking_reasons"][0])

    def test_tang_mega_138k_profile_matches_locked_hardware(self) -> None:
        profile_path = (
            SERVER_PATH.parent
            / "profiles"
            / "tang-mega-138k-som30354-dock31005-gw5ast-138c.json"
        )
        profile = server._load_board_profile(
            profile_path, self.PART_NUMBER, "GW5AST-138C"
        )
        self.assertTrue(profile["device_name_verified"])
        self.assertEqual(profile["revision"], "SOM-30354_DOCK-31005")
        self.assertEqual(len(profile["pins"]), 21)
        self.assertEqual(profile["pins"][0]["pin"], "V22")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "demo.cst").write_text("", encoding="ascii")
            project = self.write_project(root, [("demo.cst", "file.cst")])
            requests = [
                {"port": "clk", "signal": "som_sys_clk_50mhz", "role": "clock"},
                {"port": "rst_n", "signal": "dock_sys_rst_n", "role": "reset"},
                {"port": "led[0]", "signal": "dock_led_0", "role": "led"},
                {"port": "uart_rx", "signal": "dock_uart_rx", "role": "uart_rx"},
            ]
            allowed = f"{root};{profile_path.parent}"
            with patch.dict(os.environ, {"GOWIN_ALLOWED_ROOTS": allowed}):
                plan = server.gowin_plan_pins(str(project), str(profile_path), requests)
            self.assertTrue(plan["apply_ready"])
            self.assertEqual(
                [item["pin"] for item in plan["assignments"]],
                ["V22", "AA13", "T18", "V14"],
            )

    def test_build_rejects_non_ascii_project_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_root = root / "高云"
            project_root.mkdir()
            project = self.write_project(project_root, [])
            with patch.dict(os.environ, {"GOWIN_ALLOWED_ROOTS": str(root)}):
                with self.assertRaisesRegex(ValueError, "non-ASCII"):
                    server.gowin_build_project(str(project))

    def test_stdio_protocol_lists_tools(self) -> None:
        requests = "\n".join(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}}),
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
                json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
            ]
        )
        completed = subprocess.run(
            [os.sys.executable, str(SERVER_PATH)],
            input=requests + "\n",
            capture_output=True,
            text=True,
            check=True,
        )
        responses = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual(responses[0]["result"]["serverInfo"]["name"], "gowin-ide")
        names = {tool["name"] for tool in responses[1]["result"]["tools"]}
        self.assertEqual(len(names), 11)
        self.assertTrue({"gowin_start_build", "gowin_build_status", "gowin_diagnose_log"} <= names)

    def test_tool_response_keeps_windows_pipe_ascii(self) -> None:
        unicode_result = {"evidence": ["资料/原理图.pdf"]}
        with patch.object(server, "_call_tool", return_value=unicode_result):
            response = server.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "demo", "arguments": {}},
                }
            )

        self.assertIsNotNone(response)
        content = response["result"]["content"][0]["text"]
        content.encode("ascii")
        self.assertIn(r"\u8d44\u6599", content)
        self.assertEqual(json.loads(content), unicode_result)


if __name__ == "__main__":
    unittest.main()
