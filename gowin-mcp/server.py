#!/usr/bin/env python3
"""Dependency-free stdio MCP bridge for the local Gowin FPGA toolchain."""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
import xml.etree.ElementTree as ET
from collections import Counter, deque
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


SERVER_NAME = "gowin-ide"
SERVER_VERSION = "0.5.1"
REPORT_SUFFIXES = {
    ".html",
    ".json",
    ".log",
    ".result",
    ".timing_paths",
    ".txt",
}
MAX_TOOL_TEXT = 200_000
MAX_PROFILE_BYTES = 1_000_000
SAFE_IO_ATTRIBUTES = {
    "BANK_VCCIO",
    "DIFF_RESISTOR",
    "DRIVE",
    "HYSTERESIS",
    "IO_TYPE",
    "OPEN_DRAIN",
    "PCI_CLAMP",
    "PULL_MODE",
    "PULL_STRENGTH",
    "SINGLE_RESISTOR",
    "VREF",
}


TOOLS = [
    {
        "name": "gowin_start_build",
        "description": "Start one persistent, nonblocking fixed Gowin build. Returns a build_id for status polling; never programs hardware. Optional place_option/route_option are the only build settings accepted; they are checked against the tool's cmd.do and fresh reports are archived per build_id. A budget overrun warns but does not kill routing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_file": {"type": "string"},
                "stage": {"type": "string", "enum": ["syn", "pnr", "all"], "default": "all"},
                "budget_seconds": {"type": "integer", "minimum": 30, "maximum": 7200, "default": 1800},                "place_option": {"type": "integer", "minimum": 0, "maximum": 4},
                "route_option": {"type": "integer", "minimum": 0, "maximum": 2},
            },
            "required": ["project_file"], "additionalProperties": False,
        },
    },
    {
        "name": "gowin_build_status",
        "description": "Read a persistent build receipt, heartbeat, elapsed time, live log stage and bounded diagnostics. Does not cancel, restart, or infer timing acceptance.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_file": {"type": "string"}, "build_id": {"type": "string"}},
            "required": ["project_file", "build_id"], "additionalProperties": False,
        },
    },
    {
        "name": "gowin_diagnose_log",
        "description": "Read a Gowin log under the project; return exact error/warning counts, message-code groups, first error, last progress marker and log age. Also works for CLI builds without taking ownership.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_file": {"type": "string"}, "log_path": {"type": "string", "default": "build.log"},
                "max_messages": {"type": "integer", "minimum": 1, "maximum": 100, "default": 30},
            },
            "required": ["project_file"], "additionalProperties": False,
        },
    },
    {
        "name": "gowin_environment",
        "description": "Check the configured Gowin IDE, Tcl shell, and Programmer CLI paths without touching hardware.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "gowin_inspect_project",
        "description": "Parse a .gprj file and report its device, sources, constraints, and missing files.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_file": {"type": "string"}},
            "required": ["project_file"],
            "additionalProperties": False,
        },
    },
    {
        "name": "gowin_build_project",
        "description": "Run Gowin gw_sh for synthesis, place-and-route, or the full build. This writes normal project build artifacts but never programs hardware.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_file": {"type": "string"},
                "stage": {"type": "string", "enum": ["syn", "pnr", "all"], "default": "all"},
                "timeout_seconds": {"type": "integer", "minimum": 30, "maximum": 7200, "default": 1800},                "place_option": {"type": "integer", "minimum": 0, "maximum": 4},
                "route_option": {"type": "integer", "minimum": 0, "maximum": 2},            },
            "required": ["project_file"],
            "additionalProperties": False,
        },
    },
    {
        "name": "gowin_read_report",
        "description": "Read a text build report under the selected Gowin project with a bounded output size.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_file": {"type": "string"},
                "report_path": {"type": "string"},
                "max_chars": {"type": "integer", "minimum": 1000, "maximum": MAX_TOOL_TEXT, "default": 40000},
            },
            "required": ["project_file", "report_path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "gowin_timing_summary",
        "description": "Parse the newest Gowin timing report into clocks, violations, TNS, worst paths, constraint coverage, and a bounded timing status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_file": {"type": "string"},
                "max_paths": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10},
            },
            "required": ["project_file"],
            "additionalProperties": False,
        },
    },
    {
        "name": "gowin_pin_audit",
        "description": "Audit the active CST and newest final Pin Report for duplicates, missing constraints, auto-assigned ports, mismatches, and stale evidence.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_file": {"type": "string"},
                "constraint_file": {"type": "string"},
                "expected_ports": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
            },
            "required": ["project_file"],
            "additionalProperties": False,
        },
    },
    {
        "name": "gowin_plan_pins",
        "description": "Create a deterministic pin plan from an evidence-backed board profile without modifying the project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_file": {"type": "string"},
                "board_profile": {"type": "string"},
                "requests": {"type": "array", "items": {"type": "object"}, "minItems": 1},
                "constraint_file": {"type": "string"},
            },
            "required": ["project_file", "board_profile", "requests"],
            "additionalProperties": False,
        },
    },
    {
        "name": "gowin_apply_pin_plan",
        "description": "Recompute and preview or atomically apply an approved pin plan to the active CST with a timestamped backup. Never builds or programs hardware.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_file": {"type": "string"},
                "board_profile": {"type": "string"},
                "requests": {"type": "array", "items": {"type": "object"}, "minItems": 1},
                "expected_plan_id": {"type": "string"},
                "constraint_file": {"type": "string"},
                "apply": {"type": "boolean", "default": False},
            },
            "required": ["project_file", "board_profile", "requests", "expected_plan_id"],
            "additionalProperties": False,
        },
    },
]


def _gowin_home() -> Path:
    configured = os.environ.get("GOWIN_HOME", "").strip()
    if not configured or not Path(configured).is_absolute():
        raise ValueError("Set GOWIN_HOME to the absolute Gowin installation directory")
    return Path(configured).resolve()


def _allowed_roots() -> tuple[Path, ...]:
    configured = os.environ.get("GOWIN_ALLOWED_ROOTS", "")
    roots = [Path(item.strip()) for item in configured.split(";") if item.strip()]
    if not roots or any(not root.is_absolute() for root in roots):
        raise ValueError("Set GOWIN_ALLOWED_ROOTS to semicolon-separated absolute project directories")
    return tuple(root.resolve() for root in roots)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_text(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig"), "utf-8-sig"
    for encoding in ("utf-8", "gb18030"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace"), "utf-8"


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _field_name(value: str) -> str:
    value = value.lower().replace(".", "")
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


def _number(value: Any, integer: bool = False) -> int | float | None:
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value))
    if not match:
        return None
    number = float(match.group(0))
    return int(number) if integer else number


class _HtmlTables(HTMLParser):
    """Extract Gowin's simple report tables, including mildly malformed cells."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[dict[str, Any]] = []
        self._heading_tag = ""
        self._heading_chunks: list[str] = []
        self._last_heading = ""
        self._table: dict[str, Any] | None = None
        self._row: list[str] | None = None
        self._cell_chunks: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if tag in {"h1", "h2", "h3", "h4"}:
            self._heading_tag = tag
            self._heading_chunks = []
        elif tag == "table" and self._table is None:
            self._table = {"heading": self._last_heading.rstrip(":"), "rows": []}
        elif tag == "tr" and self._table is not None:
            self._finish_cell()
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._finish_cell()
            self._cell_chunks = []
        elif tag == "br" and self._cell_chunks is not None:
            self._cell_chunks.append(" ")

    def handle_data(self, data: str) -> None:
        if self._heading_tag:
            self._heading_chunks.append(data)
        if self._cell_chunks is not None:
            self._cell_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == self._heading_tag:
            self._last_heading = _clean_text("".join(self._heading_chunks))
            self._heading_tag = ""
            self._heading_chunks = []
        elif tag in {"td", "th"}:
            self._finish_cell()
        elif tag == "tr" and self._table is not None:
            self._finish_cell()
            if self._row and any(self._row):
                self._table["rows"].append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table["rows"]:
                self.tables.append(self._table)
            self._table = None
            self._row = None
            self._cell_chunks = None

    def _finish_cell(self) -> None:
        if self._cell_chunks is not None and self._row is not None:
            self._row.append(_clean_text("".join(self._cell_chunks)))
        self._cell_chunks = None


def _parse_tables(path: Path) -> list[dict[str, Any]]:
    text, _ = _read_text(path)
    parser = _HtmlTables()
    parser.feed(text)
    parser.close()
    return parser.tables


def _find_table(tables: list[dict[str, Any]], heading: str) -> dict[str, Any] | None:
    wanted = _clean_text(heading).rstrip(":").lower()
    return next((table for table in tables if table["heading"].lower() == wanted), None)


def _table_records(table: dict[str, Any] | None) -> list[dict[str, str]]:
    if not table or len(table["rows"]) < 2:
        return []
    headers = [_field_name(value) for value in table["rows"][0]]
    records = []
    for row in table["rows"][1:]:
        padded = row + [""] * max(0, len(headers) - len(row))
        records.append(dict(zip(headers, padded[: len(headers)])))
    return records


def _summary_values(table: dict[str, Any] | None) -> dict[str, str]:
    if not table:
        return {}
    return {
        _field_name(row[0]): row[1]
        for row in table["rows"]
        if len(row) >= 2 and row[0]
    }


def _validate_project(project_file: str) -> Path:
    path = Path(project_file)
    if not path.is_absolute():
        raise ValueError("project_file must be an absolute path")
    path = path.resolve()
    if path.suffix.lower() != ".gprj":
        raise ValueError("project_file must end in .gprj")
    if not path.is_file():
        raise FileNotFoundError(f"Gowin project not found: {path}")
    if not any(_is_within(path, root) for root in _allowed_roots()):
        allowed = "; ".join(str(root) for root in _allowed_roots())
        raise PermissionError(f"project_file is outside GOWIN_ALLOWED_ROOTS: {allowed}")
    return path


def _inspect_project_path(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    device = root.find("Device")
    entries = []
    missing = []
    constraints = []
    for element in root.findall("./FileList/File"):
        relative = element.get("path", "")
        source = (path.parent / Path(relative.replace("/", os.sep))).resolve()
        item = {
            "path": relative,
            "type": element.get("type", ""),
            "enabled": element.get("enable", "1") != "0",
            "exists": source.is_file(),
        }
        entries.append(item)
        if not item["exists"]:
            missing.append(relative)
        if source.suffix.lower() in {".cst", ".sdc"}:
            constraints.append(relative)
    return {
        "project_file": str(path),
        "project_name": path.stem,
        "template": root.findtext("Template", default=""),
        "format_version": root.findtext("Version", default=""),
        "device_name": device.get("name", "") if device is not None else "",
        "part_number": device.get("pn", "") if device is not None else "",
        "device_id": (device.text or "").strip() if device is not None else "",
        "files": entries,
        "constraints": constraints,
        "missing_files": missing,
    }


def _project_files(project: Path, suffix: str | None = None) -> list[Path]:
    root = ET.parse(project).getroot()
    paths = []
    for element in root.findall("./FileList/File"):
        if element.get("enable", "1") == "0":
            continue
        relative = element.get("path", "")
        path = (project.parent / Path(relative.replace("/", os.sep))).resolve()
        if suffix is None or path.suffix.lower() == suffix.lower():
            paths.append(path)
    return paths


def _constraint_path(project: Path, constraint_file: str | None = None) -> Path:
    candidates = [path for path in _project_files(project, ".cst") if path.is_file()]
    project_root = project.parent.resolve()
    if any(not _is_within(path, project_root) for path in candidates):
        raise PermissionError("enabled .cst files must stay inside the selected project")
    if constraint_file:
        requested = Path(constraint_file)
        requested = requested.resolve() if requested.is_absolute() else (project.parent / requested).resolve()
        if requested not in candidates:
            raise ValueError("constraint_file must be an enabled .cst file in the selected project")
        return requested
    if not candidates:
        raise FileNotFoundError("the project has no enabled existing .cst constraint file")
    if len(candidates) != 1:
        raise ValueError("multiple enabled .cst files found; specify constraint_file")
    return candidates[0]


def _latest_report(project: Path, patterns: tuple[str, ...]) -> Path | None:
    impl = project.parent / "impl"
    if not impl.is_dir():
        return None
    candidates: dict[Path, None] = {}
    for pattern in patterns:
        for path in impl.rglob(pattern):
            if path.is_file():
                candidates[path.resolve()] = None
    return max(candidates, key=lambda path: path.stat().st_mtime, default=None)


def _newest_project_input_mtime(project: Path) -> float:
    inputs = [project, *[path for path in _project_files(project) if path.is_file()]]
    return max(path.stat().st_mtime for path in inputs)


def _stale_evidence(project: Path, report: Path) -> bool:
    return report.stat().st_mtime + 1.0 < _newest_project_input_mtime(project)


def _artifacts(project_dir: Path, since: float | None = None) -> list[dict[str, Any]]:
    impl = project_dir / "impl"
    if not impl.is_dir():
        return []
    artifacts = []
    for path in impl.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in REPORT_SUFFIXES | {".fs", ".p", ".pr"}:
            continue
        stat = path.stat()
        if since is not None and stat.st_mtime < since:
            continue
        artifacts.append(
            {
                "path": str(path),
                "relative_path": str(path.relative_to(project_dir)),
                "bytes": stat.st_size,
                "modified_epoch": stat.st_mtime,
            }
        )
    artifacts.sort(key=lambda item: item["modified_epoch"], reverse=True)
    # This inventory is acceptance evidence, not a bounded diagnostic preview.
    # Truncating it can hide a bitstream behind newer report files.
    return artifacts


def _stage_outputs(artifacts: list[dict[str, Any]]) -> dict[str, list[str]]:
    outputs: dict[str, list[str]] = {
        name: [] for name in ("synthesis", "placement", "route", "timing", "pins", "bitstream")
    }
    for item in artifacts:
        if not item["bytes"]:
            continue
        path = Path(item["path"])
        name = path.name.lower()
        role = None
        if path.suffix.lower() in {".p", ".pr", ".fs"}:
            role = {".p": "placement", ".pr": "route", ".fs": "bitstream"}[path.suffix.lower()]
        elif name.endswith("_tr_content.html"):
            role = "timing"  # .tr.html may be only an HTML frameset wrapper.
        elif name.endswith(".pin.html"):
            role = "pins"
        elif "gwsynthesis" in path.parts and (name.endswith(".rpt.txt") or name.endswith(".rpt.html")):
            role = "synthesis"
        if role:
            outputs[role].append(item["relative_path"])
    return outputs


def gowin_environment() -> dict[str, Any]:
    home = _gowin_home()
    gw_sh = home / "IDE" / "bin" / "gw_sh.exe"
    programmer = home / "Programmer" / "bin" / "programmer_cli.exe"
    return {
        "gowin_home": str(home),
        "version_hint": home.name.removeprefix("Gowin_"),
        "gw_sh": str(gw_sh),
        "gw_sh_exists": gw_sh.is_file(),
        "programmer_cli": str(programmer),
        "programmer_cli_exists": programmer.is_file(),
        "allowed_roots": [str(root) for root in _allowed_roots()],
        "hardware_programming_exposed": False,
    }


def gowin_inspect_project(project_file: str) -> dict[str, Any]:
    return _inspect_project_path(_validate_project(project_file))


def _tcl_path(path: Path) -> str:
    value = path.as_posix()
    if any(char in value for char in "{}\r\n"):
        raise ValueError("Gowin project paths containing braces or newlines are not supported")
    return value


# The only build settings accepted from a client: bounded integers, never Tcl text.
BUILD_OPTION_RANGES = {"place_option": range(0, 5), "route_option": range(0, 3)}


def _build_options(place_option: int | None, route_option: int | None) -> dict[str, int]:
    options = {}
    for name, value in (("place_option", place_option), ("route_option", route_option)):
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value not in BUILD_OPTION_RANGES[name]:
            allowed = BUILD_OPTION_RANGES[name]
            raise ValueError(f"{name} must be an integer from {allowed.start} to {allowed.stop - 1}")
        options[name] = value
    return options


def _applied_options(project: Path) -> dict[str, int]:
    """Options the P&R tool recorded for its last run, not the ones requested."""
    command_file = project.parent / "impl" / "pnr" / "cmd.do"
    if not command_file.is_file():
        return {}
    text = command_file.read_text(encoding="utf-8", errors="replace")
    return {name: int(match[1]) for name in BUILD_OPTION_RANGES
            if (match := re.search(rf"(?m)^-{name}\s+(\d+)\s*$", text))}


def _prepare_build(project_file: str, stage: str, options: dict[str, int] | None = None) -> tuple[Path, Path, str]:
    project = _validate_project(project_file)
    try:
        str(project).encode("ascii")
    except UnicodeEncodeError as error:
        raise ValueError(
            "Gowin gw_sh V1.9.12.03 cannot reliably open non-ASCII project paths; "
            "move the project under an ASCII path such as E:\\Gowin\\workspace"
        ) from error
    if stage not in {"syn", "pnr", "all"}:
        raise ValueError("stage must be one of: syn, pnr, all")
    gw_sh = _gowin_home() / "IDE" / "bin" / "gw_sh.exe"
    if not gw_sh.is_file():
        raise FileNotFoundError(f"gw_sh.exe not found: {gw_sh}")

    settings = "".join(f"    set_option -{name} {int(value)}\n" for name, value in sorted((options or {}).items()))
    script = f"""set project_file {{{_tcl_path(project)}}}
if {{[catch {{
    open_project $project_file
{settings}    run {stage}
}} message options]}} {{
    puts stderr \"GOWIN_MCP_ERROR: $message\"
    catch {{run close}}
    exit 1
}}
run close
exit 0
"""
    missing = [str(path) for path in _project_files(project) if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Enabled project inputs missing: {missing}")
    return project, gw_sh, script


def _job_root(project: Path) -> Path:
    root = (project.parent / ".gowin-mcp").resolve()
    if not _is_within(root, project.parent):
        raise PermissionError("build metadata must stay inside the selected project")
    return root


def _job_dir(project: Path, build_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", build_id):
        raise ValueError("invalid build_id")
    directory = (_job_root(project) / build_id).resolve()
    if not _is_within(directory, _job_root(project)):
        raise PermissionError("build directory escapes metadata root")
    return directory


def _write_receipt(directory: Path, receipt: dict[str, Any]) -> None:
    temporary = directory / "receipt.tmp"
    temporary.write_text(json.dumps(receipt, ensure_ascii=True, indent=2), encoding="utf-8")
    temporary.replace(directory / "receipt.json")


def _build_inputs(project: Path) -> dict[str, str]:
    # Include memory/header/config files that often do not appear in FileList.
    paths = {project, *_project_files(project)}
    for path in project.parent.rglob("*"):
        if path.suffix.lower() in {".vh", ".svh", ".mem", ".hex", ".mi", ".ipc", ".sdc", ".cst"}:
            if not {"impl", ".gowin-mcp", "work"}.intersection(path.relative_to(project.parent).parts):
                paths.add(path.resolve())
    if any(not any(_is_within(path, root) for root in _allowed_roots()) for path in paths):
        raise PermissionError("build inputs must stay inside GOWIN_ALLOWED_ROOTS")
    return {str(path): _sha256(path) if path.is_file() else "missing" for path in sorted(paths)}


def gowin_diagnose_log(project_file: str, log_path: str = "build.log", max_messages: int = 30) -> dict[str, Any]:
    project = _validate_project(project_file)
    if not 1 <= max_messages <= 100:
        raise ValueError("max_messages must be between 1 and 100")
    path = (project.parent / log_path).resolve()
    if not _is_within(path, project.parent) or path.suffix.lower() not in {".log", ".txt"}:
        raise PermissionError("log must be a .log/.txt file inside the project")
    groups: Counter[str] = Counter()
    counts: Counter[str] = Counter()
    messages = []
    tail: deque[str] = deque(maxlen=12)
    first_error = None
    last_progress = None
    last_stage = None
    unrouted = None
    stage_patterns = (
        ("synthesis", r"Running synthesis\b|Synthesis (?:in progress|completed)"),
        ("placement", r"Running placement\b|\[\d+%\]\s*Placement Phase\b"),
        ("routing", r"Running routing\b|\[\d+%\]\s*Routing Phase\b"),
        ("timing", r"Running timing analysis\b|\[\d+%\]\s*Timing analysis completed"),
        ("bitstream", r"Bitstream generation (?:in progress|completed)"),
        ("power", r"Running power analysis\b|\[\d+%\]\s*Power analysis completed"),
    )
    with path.open(encoding="utf-8-sig", errors="replace") as handle:
        for number, line in enumerate(handle, 1):
            line = line.strip()
            tail.append(line[:2000])
            if re.match(r"\[\d+%\]|Running (?:placement|routing|timing)|.*(?:finish|completed)$", line, re.I):
                last_progress = {"line": number, "text": line[:2000]}
            for stage, pattern in stage_patterns:
                if re.match(pattern, line, re.I):
                    last_stage = {"name": stage, "line": number, "text": line[:2000]}
                    break
            match = re.search(r"\bThere are total (\d+) unrouted nets\b", line, re.I)
            if match:
                unrouted = {"count": int(match[1]), "line": number, "text": line[:2000]}
            match = re.match(r"^(WARN(?:ING)?|ERROR|FATAL|GOWIN_MCP_ERROR)\b\s*(?:\(([^)]+)\))?", line, re.I)
            if not match:
                continue
            severity = "warning" if match[1].upper().startswith("WARN") else "error"
            code = match[2] or match[1].upper()
            counts[severity] += 1
            groups[f"{severity}:{code}"] += 1
            message = {"line": number, "severity": severity, "code": code, "text": line[:2000]}
            if severity == "error" and first_error is None:
                first_error = message
            if len(messages) < max_messages:
                messages.append(message)
    stat = path.stat()
    return {"path": str(path), "bytes": stat.st_size,
            "log_age_seconds": round(max(0, time.time() - stat.st_mtime), 3),
            "error_count": counts["error"], "warning_count": counts["warning"],
            "groups": dict(groups), "messages": messages,
            "messages_truncated": sum(counts.values()) > len(messages),
            "first_error": first_error, "last_progress": last_progress, "last_stage": last_stage,
            "unrouted_nets": unrouted["count"] if unrouted else None,
            "unrouted_evidence": unrouted, "tail": list(tail),
            "process_state": "not-probed", "evidence_level": "log-only"}


def gowin_start_build(project_file: str, stage: str = "all", budget_seconds: int = 1800,
                      place_option: int | None = None, route_option: int | None = None) -> dict[str, Any]:
    options = _build_options(place_option, route_option)
    if options and stage == "syn":
        raise ValueError("place_option/route_option apply to pnr or all, not syn")
    project, _, _ = _prepare_build(project_file, stage, options)
    if not 30 <= budget_seconds <= 7200:
        raise ValueError("budget_seconds must be between 30 and 7200")
    inputs = _build_inputs(project)
    root = _job_root(project)
    root.mkdir(exist_ok=True)
    lock = root / "build.lock"
    build_id = uuid.uuid4().hex
    # Exclusive creation also prevents two MCP clients from writing one impl/.
    try:
        with lock.open("x", encoding="ascii") as handle:
            handle.write(build_id)
    except FileExistsError as error:
        raise RuntimeError("A managed build owns this project directory; inspect its receipt before any restart. "
                           f"Lock: {lock}") from error
    directory = _job_dir(project, build_id)
    try:
        directory.mkdir()
        receipt = {"build_id": build_id, "project_file": str(project), "stage": stage,
                   "budget_seconds": budget_seconds, "options": options, "started_epoch": time.time(),
                   "heartbeat_epoch": time.time(), "state": "starting", "success": False,
                   "evidence_level": "build-running", "inputs": inputs,
                   "fingerprint_scope": "enabled inputs plus in-project headers/memory/constraints/IP config; external implicit includes not covered",
                   "requires_report_review": True}
        _write_receipt(directory, receipt)
        with (directory / "worker.log").open("wb") as output:
            options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
            subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--build-worker", str(project), build_id],
                             cwd=project.parent, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                             **options)
    except Exception as error:
        if (directory / "receipt.json").is_file():
            receipt.update(state="failed", success=False, error=str(error), evidence_level="build-failed",
                           finished_epoch=time.time(), heartbeat_epoch=time.time())
            _write_receipt(directory, receipt)
        lock.unlink(missing_ok=True)
        raise
    return gowin_build_status(str(project), build_id)


def gowin_build_status(project_file: str, build_id: str) -> dict[str, Any]:
    project = _validate_project(project_file)
    directory = _job_dir(project, build_id)
    receipt = json.loads((directory / "receipt.json").read_text(encoding="utf-8"))
    if receipt["project_file"] != str(project) or receipt["build_id"] != build_id:
        raise ValueError("build receipt does not match selected project and id")
    now = time.time()
    elapsed = receipt.get("finished_epoch", now) - receipt["started_epoch"]
    result = {key: value for key, value in receipt.items() if key != "inputs"}
    result.update(elapsed_seconds=round(elapsed, 3), budget_exceeded=elapsed > receipt["budget_seconds"],
                  receipt_path=str(directory / "receipt.json"),
                  heartbeat_age_seconds=round(max(0, now - receipt["heartbeat_epoch"]), 3))
    if receipt["state"] in {"starting", "running"} and result["heartbeat_age_seconds"] > 30:
        result["state"] = "unknown"
        result["note"] = "Worker heartbeat is stale; build liveness is unknown. Do not restart or clear lock without checking the owned process."
    if (directory / "build.log").is_file():
        result["log"] = gowin_diagnose_log(str(project), str(directory / "build.log"))
    if receipt["state"] in {"completed", "failed"}:
        result["inputs_match_now"] = _build_inputs(project) == receipt["inputs"]
        result["artifacts_match_now"] = all(
            _is_within(Path(item["path"]).resolve(), project.parent)
            and Path(item["path"]).is_file() and _sha256(Path(item["path"])) == item.get("sha256")
            for item in receipt.get("new_artifacts", []))
        if not result["inputs_match_now"] or not result["artifacts_match_now"]:
            result.update(success=False, evidence_level="stale-build")
    return result


def _build_worker(project_file: str, build_id: str) -> int:
    project = _validate_project(project_file)
    directory = _job_dir(project, build_id)
    lock = _job_root(project) / "build.lock"
    if lock.read_text(encoding="ascii") != build_id:
        raise ValueError("worker does not own project build lock")
    receipt = json.loads((directory / "receipt.json").read_text(encoding="utf-8"))
    if receipt["project_file"] != str(project) or receipt["build_id"] != build_id or receipt["state"] != "starting":
        raise ValueError("invalid worker receipt")
    process = None
    try:
        _, executable, script = _prepare_build(str(project), receipt["stage"], receipt.get("options"))
        if _build_inputs(project) != receipt["inputs"]:
            raise ValueError("project inputs changed before worker start")
        script_path = directory / "build.tcl"
        script_path.write_text(script, encoding="utf-8")
        with (directory / "build.log").open("wb") as output:
            options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
            process = subprocess.Popen([str(executable), str(script_path)], cwd=project.parent,
                                       stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, **options)
            receipt.update(state="running", worker_pid=os.getpid(), tool_pid=process.pid)
            while True:
                receipt["heartbeat_epoch"] = time.time()
                _write_receipt(directory, receipt)
                try:
                    code = process.wait(timeout=5)
                    break
                except subprocess.TimeoutExpired:
                    continue
        log = gowin_diagnose_log(str(project), str(directory / "build.log"))
        fresh = _artifacts(project.parent, since=receipt["started_epoch"])
        outputs = _stage_outputs(fresh)
        required = ("synthesis",) if receipt["stage"] == "syn" else ("route", "timing", "pins", "bitstream")
        missing = [role for role in required if not outputs[role]]
        bitstreams = [item for item in fresh if item["relative_path"] in outputs["bitstream"]]
        unchanged = _build_inputs(project) == receipt["inputs"]
        requested = receipt.get("options") or {}
        applied = _applied_options(project) if receipt["stage"] != "syn" else {}
        options_applied = all(applied.get(name) == value for name, value in requested.items())
        success = (code == 0 and log["error_count"] == 0 and log["unrouted_nets"] in {None, 0}
                   and not missing and unchanged and options_applied)
        # The next run overwrites impl/; keep this run's reports, failed or not.
        # Large binary placement/route/bitstream files stay in place, hash only.
        archive = directory / "reports"
        for item in fresh:
            item["sha256"] = _sha256(Path(item["path"]))
            if Path(item["path"]).suffix.lower() in REPORT_SUFFIXES:
                target = archive / item["relative_path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item["path"], target)
        receipt.update(state="completed" if success else "failed", success=success, return_code=code,
                       inputs_unchanged=unchanged, new_bitstreams=bitstreams, new_artifacts=fresh,
                       stage_outputs=outputs, missing_outputs=missing,
                       applied_options=applied, options_applied=options_applied,
                       report_archive=str(archive) if archive.is_dir() else None,
                       evidence_level=("synthesized" if receipt["stage"] == "syn" else "bitstream-generated")
                       if success else "build-failed")
    except Exception as error:
        still_running = process is not None and process.poll() is None
        receipt.update(state="unknown" if still_running else "failed", success=False,
                       error=str(error), evidence_level="build-incomplete" if still_running else "build-failed")
    finally:
        receipt.update(finished_epoch=time.time(), heartbeat_epoch=time.time())
        _write_receipt(directory, receipt)
        # Never release ownership if an exception left the child still running.
        if process is None or process.poll() is not None:
            if lock.read_text(encoding="ascii") == build_id:
                lock.unlink()
    return 0 if receipt["success"] else 1


def gowin_build_project(project_file: str, stage: str = "all", timeout_seconds: int = 1800,
                        place_option: int | None = None, route_option: int | None = None) -> dict[str, Any]:
    """Compatibility call: timeout stops waiting, never destroys a live route."""
    if not 30 <= timeout_seconds <= 7200:
        raise ValueError("timeout_seconds must be between 30 and 7200")
    result = gowin_start_build(project_file, stage, timeout_seconds, place_option, route_option)
    deadline = time.monotonic() + timeout_seconds
    while result["state"] in {"starting", "running"} and time.monotonic() < deadline:
        time.sleep(0.5)
        result = gowin_build_status(project_file, result["build_id"])
    if result["state"] in {"starting", "running", "unknown"}:
        result["wait_timed_out"] = True
    return result


def _clock_name_from_sdc(command: str) -> str | None:
    match = re.search(r"(?:^|\s)-name\s+(?:\{([^}]+)\}|\"([^\"]+)\"|(\S+))", command)
    if match:
        return next(value for value in match.groups() if value)
    match = re.search(r"\[get_(?:ports|pins)\s+\{?([^}\]]+)\}?\]", command)
    return match.group(1).strip() if match else None


def _timing_paths(table: dict[str, Any] | None, limit: int) -> list[dict[str, Any]]:
    paths = []
    for record in _table_records(table):
        paths.append(
            {
                "number": _number(record.get("path_number"), integer=True),
                "slack_ns": _number(record.get("path_slack")),
                "from_node": record.get("from_node", ""),
                "to_node": record.get("to_node", ""),
                "from_clock": record.get("from_clock", ""),
                "to_clock": record.get("to_clock", ""),
                "relationship_ns": _number(record.get("relation")),
                "clock_skew_ns": _number(record.get("clock_skew")),
                "data_delay_ns": _number(record.get("data_delay")),
            }
        )
    paths.sort(key=lambda item: float("inf") if item["slack_ns"] is None else item["slack_ns"])
    return paths[:limit]


def _timing_path_table(tables: list[dict[str, Any]], analysis: str) -> dict[str, Any] | None:
    table = _find_table(tables, f"{analysis.title()} Paths Table")
    if table is not None:
        return table
    command = re.compile(rf"\breport_timing\s+-{re.escape(analysis)}(?:\s|$)", re.IGNORECASE)
    return next((item for item in tables if command.search(item["heading"])), None)


_PATH_DETAIL = re.compile(
    r"Slack (-?[\d.]+) (?:.*? )?From (\S+) To (\S+) .*?Logic Level (\d+) .*?"
    r"Arrival Data Path Delay cell: [\d.]+, [\d.]+%; route: [\d.]+, ([\d.]+)%")


def _signal_root(node: str) -> str:
    """u_x/voice_stealing_18_s1 -> u_x/voice_stealing: one name per register bank."""
    node = re.sub(r"(?:_\d+)*_s\d*$", "", re.sub(r"/[A-Z0-9]+$", "", node))
    return re.sub(r"\[\d+\]", "[*]", node)


def _setup_clusters(report: Path) -> list[dict[str, Any]]:
    """Group the setup paths the report lists by start and end register bank.

    Covers only the paths Gowin printed (report_timing -max_paths), so counts
    describe that sample, not every violating endpoint in the design.
    """
    text, _ = _read_text(report)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>|&nbsp;?", " ", text))
    start = text.find("Setup Analysis Report")
    if start < 0:
        return []
    end = text.find("Hold Analysis Report", start)
    clusters: dict[tuple[str, str], dict[str, Any]] = {}
    # One search per printed path, so a lazy match can never span two paths.
    details = (_PATH_DETAIL.search(chunk) for chunk in re.split(r"\bPath\d+\b", text[start:end if end > 0 else None]))
    for slack, source, target, levels, route in (match.groups() for match in details if match):
        entry = clusters.setdefault((_signal_root(source), _signal_root(target)),
                                    {"paths": 0, "violating_paths": 0, "slacks": [], "route": [], "levels": 0})
        entry["paths"] += 1
        entry["violating_paths"] += float(slack) < 0
        entry["slacks"].append(float(slack))
        entry["route"].append(float(route))
        entry["levels"] = max(entry["levels"], int(levels))
    result = [{"from": key[0], "to": key[1], "paths": entry["paths"], "violating_paths": entry["violating_paths"],
               "worst_slack_ns": min(entry["slacks"]), "max_logic_levels": entry["levels"],
               "mean_route_delay_percent": round(sum(entry["route"]) / len(entry["route"]), 1)}
              for key, entry in clusters.items()]
    result.sort(key=lambda item: item["worst_slack_ns"])
    return result


def _command_table(tables: list[dict[str, Any]], command: str) -> dict[str, Any] | None:
    """Gowin heads an optional report table with its "Report Command:<command> ..." line."""
    return next((table for table in tables if re.search(rf"\b{re.escape(command)}\b", table["heading"])), None)


def gowin_timing_summary(project_file: str, max_paths: int = 10) -> dict[str, Any]:
    project = _validate_project(project_file)
    max_paths = int(max_paths)
    if not 1 <= max_paths <= 100:
        raise ValueError("max_paths must be between 1 and 100")
    report = _latest_report(project, ("*_tr_content.html",))
    if report is None:
        report = _latest_report(project, ("*.tr.html",))
    if report is None:
        raise FileNotFoundError("no Gowin timing HTML report found under impl")

    tables = _parse_tables(report)
    sta = _summary_values(_find_table(tables, "STA Tool Run Summary"))
    clocks = []
    for record in _table_records(_find_table(tables, "Clock Summary")):
        clocks.append(
            {
                "name": record.get("clock_name", ""),
                "type": record.get("type", ""),
                "period_ns": _number(record.get("period")),
                "frequency_mhz": _number(record.get("frequency_mhz")),
                "rise_ns": _number(record.get("rise")),
                "fall_ns": _number(record.get("fall")),
                "source": record.get("source", ""),
                "master": record.get("master", ""),
                "objects": record.get("objects", ""),
            }
        )

    fmax = []
    for record in _table_records(_find_table(tables, "Max Frequency Summary")):
        constraint = _number(record.get("constraint"))
        actual = _number(record.get("actual_fmax"))
        fmax.append(
            {
                "clock": record.get("clock_name", ""),
                "constraint_mhz": constraint,
                "actual_fmax_mhz": actual,
                "margin_mhz": None if constraint is None or actual is None else round(actual - constraint, 6),
                "logic_levels": _number(record.get("logic_level"), integer=True),
                "entity": record.get("entity", ""),
            }
        )

    tns = []
    for record in _table_records(_find_table(tables, "Total Negative Slack Summary")):
        tns.append(
            {
                "clock": record.get("clock_name", ""),
                "analysis": record.get("analysis_type", ""),
                "tns_ns": _number(record.get("endpoints_tns")),
                "violated_endpoints": _number(record.get("number_of_endpoints"), integer=True),
            }
        )

    setup_paths = _timing_paths(_timing_path_table(tables, "setup"), max_paths)
    hold_paths = _timing_paths(_timing_path_table(tables, "hold"), max_paths)
    constraint_records = _table_records(_find_table(tables, "Timing Constraints Report"))
    constraints = [
        {
            "type": record.get("sdc_command_type", ""),
            "state": record.get("state", ""),
            "command": record.get("detail_command", ""),
        }
        for record in constraint_records
    ]
    explicit_clocks = {
        name
        for constraint in constraints
        if constraint["state"].lower().startswith("activ")
        and (name := _clock_name_from_sdc(constraint["command"]))
    }
    coverage_gaps = [clock["name"] for clock in clocks if clock["name"] and clock["name"] not in explicit_clocks]

    setup_violations = _number(sta.get("numbers_of_setup_violated_endpoints"), integer=True)
    hold_violations = _number(sta.get("numbers_of_hold_violated_endpoints"), integer=True)
    paths_analyzed = _number(sta.get("numbers_of_paths_analyzed"), integer=True)
    endpoints_analyzed = _number(sta.get("numbers_of_endpoints_analyzed"), integer=True)
    worst_setup = setup_paths[0]["slack_ns"] if setup_paths else None
    worst_hold = hold_paths[0]["slack_ns"] if hold_paths else None
    # Missing report fields are unknown, never zero violations. A wrapper or
    # partial report must not turn into a timing pass just because clocks exist.
    missing_timing_data = [name for name, value in (
        ("setup_violated_endpoints", setup_violations),
        ("hold_violated_endpoints", hold_violations),
    ) if value is None or value < 0]
    missing_timing_data.extend(name for name, value in (
        ("paths_analyzed", paths_analyzed), ("endpoints_analyzed", endpoints_analyzed),
    ) if value is None or value <= 0)
    missing_timing_data.extend(name for name, value in (
        ("worst_setup_slack_ns", worst_setup), ("worst_hold_slack_ns", worst_hold),
    ) if value is None)
    if any(clock["period_ns"] is None or clock["period_ns"] <= 0 for clock in clocks):
        missing_timing_data.append("clock_periods")
    all_slacks = [
        path["slack_ns"]
        for path in [*setup_paths, *hold_paths]
        if path["slack_ns"] is not None
    ]
    violated = any(value is not None and value > 0 for value in (setup_violations, hold_violations))
    violated = violated or any(slack < 0 for slack in all_slacks)
    violated = violated or any(item["tns_ns"] is not None and item["tns_ns"] < 0 for item in tns)
    stale = _stale_evidence(project, report)
    if stale:
        status = "stale"
    elif violated:
        status = "violated"
    elif not clocks:
        status = "no-clock-data"
    elif missing_timing_data:
        status = "incomplete"
    elif coverage_gaps:
        status = "met-with-coverage-gaps"
    else:
        status = "met"

    return {
        "project_file": str(project),
        "report_path": str(report),
        "report_modified_epoch": report.stat().st_mtime,
        "source_newer_than_report": stale,
        "status": status,
        "timing_constraints_met": not stale and not violated and bool(clocks) and not missing_timing_data,
        "timing_clean": status == "met",
        "missing_timing_data": missing_timing_data,
        "sta": {
            "setup_delay_model": sta.get("setup_delay_model", ""),
            "hold_delay_model": sta.get("hold_delay_model", ""),
            "paths_analyzed": paths_analyzed,
            "endpoints_analyzed": endpoints_analyzed,
            "setup_violated_endpoints": setup_violations,
            "hold_violated_endpoints": hold_violations,
        },
        "worst_setup_slack_ns": worst_setup,
        "worst_hold_slack_ns": worst_hold,
        "clocks": clocks,
        "max_frequency": fmax,
        "total_negative_slack": tns,
        "worst_paths": {"setup": setup_paths, "hold": hold_paths},
        "setup_clusters": _setup_clusters(report),
        # Present only when the SDC asks for them (SUG940 5.5.2/5.5.3):
        #   report_high_fanout_nets -max_nets N [-min_fanout F]
        #   report_route_congestion -max_grids N [-min_route_congestion R]
        "high_fanout_nets": [
            {"fanout": _number(record.get("fanout"), integer=True), "net": record.get("net_name", ""),
             "worst_slack_ns": _number(record.get("worst_slack")), "max_delay_ns": _number(record.get("max_delay"))}
            for record in _table_records(_command_table(tables, "report_high_fanout_nets"))],
        "route_congestion": [
            {"grid": record.get("grid_loc", ""),
             "congestion_percent": _number(str(record.get("route_congestions", "")).rstrip("%"))}
            for record in _table_records(_command_table(tables, "report_route_congestion"))],
        "setup_paths_reported": len(_table_records(_timing_path_table(tables, "setup"))),
        "constraints": constraints,
        "explicitly_constrained_clocks": sorted(explicit_clocks),
        "clocks_without_explicit_sdc": coverage_gaps,
        "notes": [
            "A clock missing an explicit SDC command is a coverage warning, not proof that every path on it is unconstrained."
        ] if coverage_gaps else [],
    }


_CST_LOC = re.compile(r'^\s*IO_LOC\s+"([^"]+)"\s+([^;]+);', re.IGNORECASE)
_CST_PORT = re.compile(r'^\s*IO_PORT\s+"([^"]+)"\s+([^;]+);', re.IGNORECASE)
_CST_ATTRIBUTE = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)=("[^"]*"|[^\s]+)')


def _validate_port_name(port: str) -> str:
    port = str(port).strip()
    if not port or any(character in port for character in '";\r\n'):
        raise ValueError(f"invalid port name: {port!r}")
    return port


def _split_pins(value: str) -> list[str]:
    pins = [item.strip() for item in str(value).split(",") if item.strip()]
    if not pins or any(not re.fullmatch(r"[A-Za-z0-9_]+", pin) for pin in pins):
        raise ValueError(f"invalid package pin expression: {value!r}")
    return pins


def _parse_io_attributes(value: str | dict[str, Any], restrict: bool = True) -> dict[str, str]:
    if isinstance(value, dict):
        items = value.items()
    else:
        items = _CST_ATTRIBUTE.findall(value)
    attributes = {}
    for raw_key, raw_value in items:
        key = str(raw_key).upper()
        item = str(raw_value).strip().strip('"')
        if restrict and key not in SAFE_IO_ATTRIBUTES:
            raise ValueError(f"unsupported IO_PORT attribute: {key}")
        if not item or not re.fullmatch(r"[A-Za-z0-9_.+/-]+", item):
            raise ValueError(f"invalid value for {key}: {item!r}")
        attributes[key] = item
    return attributes


def _parse_cst(path: Path) -> dict[str, Any]:
    text, encoding = _read_text(path)
    locations: list[dict[str, Any]] = []
    io_ports: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if match := _CST_LOC.match(line):
            locations.append(
                {
                    "port": match.group(1),
                    "pin": match.group(2).strip(),
                    "pins": _split_pins(match.group(2)),
                    "line": line_number,
                }
            )
        elif match := _CST_PORT.match(line):
            io_ports.append(
                {
                    "port": match.group(1),
                    "attributes": _parse_io_attributes(match.group(2), restrict=False),
                    "line": line_number,
                }
            )

    port_counts: dict[str, int] = {}
    pin_ports: dict[str, set[str]] = {}
    for location in locations:
        port_counts[location["port"]] = port_counts.get(location["port"], 0) + 1
        for pin in location["pins"]:
            pin_ports.setdefault(pin.upper(), set()).add(location["port"])
    io_port_counts: dict[str, int] = {}
    for item in io_ports:
        io_port_counts[item["port"]] = io_port_counts.get(item["port"], 0) + 1
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "encoding": encoding,
        "text": text,
        "locations": locations,
        "io_ports": io_ports,
        "duplicate_location_ports": sorted(port for port, count in port_counts.items() if count > 1),
        "duplicate_io_ports": sorted(port for port, count in io_port_counts.items() if count > 1),
        "duplicate_pins": [
            {"pin": pin, "ports": sorted(ports)}
            for pin, ports in sorted(pin_ports.items())
            if len(ports) > 1
        ],
    }


def _pin_report(project: Path) -> tuple[Path | None, dict[str, Any]]:
    report = _latest_report(project, ("*.pin.html",))
    if report is None:
        return None, {"metadata": {}, "ports": []}
    tables = _parse_tables(report)
    metadata = _summary_values(_find_table(tables, "Pin Messages"))
    ports = []
    for record in _table_records(_find_table(tables, "Pinout by Port Name")):
        location = record.get("loc_bank", "")
        pin, separator, bank = location.rpartition("/")
        if not separator:
            pin, bank = location, ""
        ports.append(
            {
                "port": record.get("port_name", ""),
                "diff_pair": record.get("diff_pair", ""),
                "pin": pin,
                "pins": _split_pins(pin) if pin and pin != "-" else [],
                "bank": bank,
                "constrained": record.get("constraint", "").upper() == "Y",
                "direction": record.get("dir", ""),
                "site": record.get("site", ""),
                "config_functions": record.get("cfg", ""),
                "io_type": record.get("io_type", ""),
                "drive": record.get("drive", ""),
                "pull_mode": record.get("pull_mode", ""),
                "bank_vccio": record.get("bankvccio", ""),
            }
        )
    return report, {"metadata": metadata, "ports": ports}


def gowin_pin_audit(
    project_file: str,
    constraint_file: str | None = None,
    expected_ports: list[str] | None = None,
) -> dict[str, Any]:
    project = _validate_project(project_file)
    cst_path = _constraint_path(project, constraint_file)
    cst = _parse_cst(cst_path)
    report_path, final = _pin_report(project)
    cst_by_port = {item["port"]: item for item in cst["locations"]}
    attributes_by_port = {item["port"]: item for item in cst["io_ports"]}
    final_by_port = {item["port"]: item for item in final["ports"]}

    mismatches = []
    for port in sorted(cst_by_port.keys() & final_by_port.keys()):
        expected = [pin.upper() for pin in cst_by_port[port]["pins"]]
        actual = [pin.upper() for pin in final_by_port[port]["pins"]]
        if expected != actual:
            mismatches.append({"port": port, "cst_pins": expected, "final_pins": actual})
    expected = [_validate_port_name(port) for port in (expected_ports or [])]
    report_stale = bool(report_path and _stale_evidence(project, report_path))
    report_part = final["metadata"].get("part_number", "")
    project_part = _inspect_project_path(project)["part_number"]
    expected_without_location = sorted(set(expected) - cst_by_port.keys())
    ports_without_attributes = sorted(cst_by_port.keys() - attributes_by_port.keys())
    final_ports_without_cst = sorted(final_by_port.keys() - cst_by_port.keys())
    cst_ports_missing_from_final = sorted(cst_by_port.keys() - final_by_port.keys()) if report_path else []
    auto_assigned_ports = sorted(
        port for port, item in final_by_port.items() if port not in cst_by_port or not item["constrained"]
    )
    issues = []
    if cst["duplicate_location_ports"]:
        issues.append("duplicate IO_LOC declarations")
    if cst["duplicate_io_ports"]:
        issues.append("duplicate IO_PORT declarations")
    if cst["duplicate_pins"]:
        issues.append("package pins assigned to multiple ports")
    if mismatches:
        issues.append("CST and final Pin Report locations differ")
    if expected_without_location:
        issues.append("expected ports are missing IO_LOC declarations")
    if ports_without_attributes:
        issues.append("CST ports are missing IO_PORT attributes")
    if report_path is None:
        issues.append("final Pin Report is missing")
    if final_ports_without_cst:
        issues.append("final Pin Report contains ports without CST locations")
    if cst_ports_missing_from_final:
        issues.append("CST ports are missing from the final Pin Report")
    if auto_assigned_ports:
        issues.append("final Pin Report contains auto-assigned ports")
    if report_stale:
        issues.append("final Pin Report is older than a project input")
    if report_part and report_part != project_part:
        issues.append("final Pin Report part number differs from the project")

    return {
        "project_file": str(project),
        "project_part_number": project_part,
        "constraint_file": str(cst_path),
        "constraint_sha256": cst["sha256"],
        "constraint_assignments": [
            {
                **location,
                "attributes": attributes_by_port.get(location["port"], {}).get("attributes", {}),
            }
            for location in cst["locations"]
        ],
        "duplicate_location_ports": cst["duplicate_location_ports"],
        "duplicate_io_ports": cst["duplicate_io_ports"],
        "duplicate_pins": cst["duplicate_pins"],
        "expected_ports_without_location": expected_without_location,
        "ports_without_io_attributes": ports_without_attributes,
        "final_report": str(report_path) if report_path else None,
        "final_report_stale": report_stale,
        "final_report_part_number": report_part or None,
        "final_ports": final["ports"],
        "final_ports_without_cst": final_ports_without_cst,
        "cst_ports_missing_from_final": cst_ports_missing_from_final,
        "auto_assigned_ports": auto_assigned_ports,
        "location_mismatches": mismatches,
        "issues": issues,
        "clean": not issues,
    }


def _profile_path(project: Path, board_profile: str) -> Path:
    requested = Path(board_profile)
    path = requested.resolve() if requested.is_absolute() else (project.parent / requested).resolve()
    if path.suffix.lower() != ".json" or not path.is_file():
        raise FileNotFoundError(f"board profile JSON not found: {path}")
    if not any(_is_within(path, root) for root in _allowed_roots()):
        raise PermissionError("board_profile is outside GOWIN_ALLOWED_ROOTS")
    if path.stat().st_size > MAX_PROFILE_BYTES:
        raise ValueError("board_profile is too large")
    return path


def _load_board_profile(path: Path, part_number: str, device_name: str) -> dict[str, Any]:
    profile = json.loads(path.read_text(encoding="utf-8-sig"))
    if profile.get("schema_version") != 1:
        raise ValueError("board_profile schema_version must be 1")
    for field in ("board", "revision", "part_number", "evidence", "pins"):
        if not profile.get(field):
            raise ValueError(f"board_profile requires {field}")
    if profile["part_number"] != part_number:
        raise ValueError(
            f"board_profile part_number {profile['part_number']} does not match project {part_number}"
        )
    profile_device = str(profile.get("device_name", "")).strip()
    if profile_device and profile_device != device_name:
        raise ValueError(
            f"board_profile device_name {profile_device} does not match project {device_name}"
        )
    if not isinstance(profile["evidence"], list) or not all(str(item).strip() for item in profile["evidence"]):
        raise ValueError("board_profile evidence must be a non-empty list")
    if not isinstance(profile["pins"], list):
        raise ValueError("board_profile pins must be a list")

    root_defaults = _parse_io_attributes(profile.get("default_attributes", {}))
    normalized = []
    seen: dict[str, str] = {}
    for index, raw in enumerate(profile["pins"]):
        if not isinstance(raw, dict) or not raw.get("pin"):
            raise ValueError(f"board_profile pin entry {index} requires pin")
        pins = _split_pins(raw["pin"])
        for pin in pins:
            key = pin.upper()
            if key in seen:
                raise ValueError(f"board_profile package pin {pin} is declared more than once")
            seen[key] = str(raw.get("signal", ""))
        roles = [str(role).lower() for role in raw.get("roles", [])]
        attributes = {**root_defaults, **_parse_io_attributes(raw.get("attributes", {}))}
        normalized.append(
            {
                "pin": ",".join(pins),
                "pins": pins,
                "signal": str(raw.get("signal", "")),
                "roles": roles,
                "bank": str(raw.get("bank", "")),
                "reserved": bool(raw.get("reserved", False)),
                "priority": int(raw.get("priority", index)),
                "attributes": attributes,
                "notes": str(raw.get("notes", "")),
            }
        )
    profile["pins"] = normalized
    profile["path"] = str(path)
    profile["sha256"] = _sha256(path)
    profile["device_name_verified"] = profile_device == device_name
    return profile


def _normalize_requests(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(requests, list) or not requests:
        raise ValueError("requests must be a non-empty array")
    normalized = []
    ports = set()
    allowed = {"port", "signal", "role", "pin", "attributes"}
    for index, request in enumerate(requests):
        if not isinstance(request, dict):
            raise ValueError(f"pin request {index} must be an object")
        unknown = set(request) - allowed
        if unknown:
            raise ValueError(f"unsupported pin request fields: {', '.join(sorted(unknown))}")
        port = _validate_port_name(request.get("port", ""))
        if port in ports:
            raise ValueError(f"duplicate requested port: {port}")
        ports.add(port)
        normalized.append(
            {
                "port": port,
                "signal": str(request.get("signal", "")),
                "role": str(request.get("role", "gpio")).lower(),
                "pin": str(request.get("pin", "")),
                "attributes": _parse_io_attributes(request.get("attributes", {})),
            }
        )
    return normalized


def _plan_pins(
    project: Path,
    board_profile: str,
    requests: list[dict[str, Any]],
    constraint_file: str | None,
) -> dict[str, Any]:
    project_info = _inspect_project_path(project)
    cst_path = _constraint_path(project, constraint_file)
    if not _is_within(cst_path, project.parent.resolve()):
        raise PermissionError("the writable CST must stay inside the selected project")
    cst = _parse_cst(cst_path)
    if cst["duplicate_location_ports"] or cst["duplicate_io_ports"]:
        raise ValueError("CST has duplicate port declarations; run gowin_pin_audit and repair them first")
    profile_path = _profile_path(project, board_profile)
    profile = _load_board_profile(
        profile_path, project_info["part_number"], project_info["device_name"]
    )
    requested = _normalize_requests(requests)
    requested_ports = {item["port"] for item in requested}
    unresolved_duplicates = [
        item for item in cst["duplicate_pins"]
        if len(set(item["ports"]) - requested_ports) > 1
    ]
    if unresolved_duplicates:
        raise ValueError("CST has duplicate package-pin assignments outside this plan; run gowin_pin_audit first")
    used = {
        pin.upper(): location["port"]
        for location in cst["locations"]
        if location["port"] not in requested_ports
        for pin in location["pins"]
    }
    assignments = []
    for request in requested:
        candidates = []
        requested_pins = [pin.upper() for pin in _split_pins(request["pin"])] if request["pin"] else []
        for pin in profile["pins"]:
            pin_keys = [item.upper() for item in pin["pins"]]
            if pin["reserved"] or any(item in used for item in pin_keys):
                continue
            if requested_pins and requested_pins != pin_keys:
                continue
            if request["signal"] and request["signal"] != pin["signal"]:
                continue
            if request["role"] and request["role"] not in pin["roles"]:
                continue
            requested_voltage = request["attributes"].get("BANK_VCCIO")
            profile_voltage = pin["attributes"].get("BANK_VCCIO")
            if requested_voltage and profile_voltage and requested_voltage != profile_voltage:
                continue
            requested_type = request["attributes"].get("IO_TYPE")
            profile_type = pin["attributes"].get("IO_TYPE")
            if requested_type and profile_type and requested_type.upper() != profile_type.upper():
                continue
            candidates.append(pin)
        if not candidates:
            raise ValueError(
                f"no safe board-profile pin satisfies port {request['port']} "
                f"(signal={request['signal'] or '-'}, role={request['role']})"
            )
        selected = min(candidates, key=lambda item: (item["priority"], item["pin"]))
        attributes = {**selected["attributes"], **request["attributes"]}
        for required in ("IO_TYPE", "BANK_VCCIO"):
            if required not in attributes:
                raise ValueError(f"pin {selected['pin']} for {request['port']} lacks required {required}")
        for pin in selected["pins"]:
            used[pin.upper()] = request["port"]
        assignments.append(
            {
                "port": request["port"],
                "pin": selected["pin"],
                "pins": selected["pins"],
                "signal": selected["signal"],
                "role": request["role"],
                "bank": selected["bank"],
                "attributes": attributes,
                "notes": selected["notes"],
            }
        )

    payload = {
        "project_file": str(project),
        "device_name": project_info["device_name"],
        "part_number": project_info["part_number"],
        "constraint_file": str(cst_path),
        "constraint_sha256": cst["sha256"],
        "board_profile": str(profile_path),
        "board_profile_sha256": profile["sha256"],
        "assignments": assignments,
    }
    plan_id = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    blocking_reasons = []
    if str(profile["revision"]).strip().lower() in {"unknown", "tbd", "?"}:
        blocking_reasons.append("board profile revision is unresolved")
    if not profile["device_name_verified"]:
        blocking_reasons.append("board profile does not declare the exact project device_name")
    return {
        **payload,
        "plan_id": plan_id,
        "board": profile["board"],
        "revision": profile["revision"],
        "evidence": profile["evidence"],
        "apply_ready": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
    }


def gowin_plan_pins(
    project_file: str,
    board_profile: str,
    requests: list[dict[str, Any]],
    constraint_file: str | None = None,
) -> dict[str, Any]:
    return _plan_pins(_validate_project(project_file), board_profile, requests, constraint_file)


def _format_attributes(attributes: dict[str, str]) -> str:
    preferred = ["IO_TYPE", "PULL_MODE", "DRIVE", "BANK_VCCIO"]
    keys = [key for key in preferred if key in attributes]
    keys.extend(sorted(set(attributes) - set(keys)))
    return " ".join(f"{key}={attributes[key]}" for key in keys)


def _trailing_comment(line: str) -> str:
    semicolon = line.find(";")
    comment = line.find("//", semicolon + 1)
    return line[comment:].strip() if comment >= 0 else ""


def _render_cst(text: str, assignments: list[dict[str, Any]], plan_id: str) -> str:
    by_port = {item["port"]: item for item in assignments}
    location_written: set[str] = set()
    attributes_written: set[str] = set()
    newline = "\r\n" if "\r\n" in text else "\n"
    rendered = []
    for line in text.splitlines():
        if (match := _CST_LOC.match(line)) and match.group(1) in by_port:
            assignment = by_port[match.group(1)]
            comment = _trailing_comment(line)
            value = f'IO_LOC "{assignment["port"]}" {assignment["pin"]};'
            rendered.append(value + (f"  {comment}" if comment else ""))
            location_written.add(assignment["port"])
        elif (match := _CST_PORT.match(line)) and match.group(1) in by_port:
            assignment = by_port[match.group(1)]
            comment = _trailing_comment(line)
            value = f'IO_PORT "{assignment["port"]}" {_format_attributes(assignment["attributes"])};'
            rendered.append(value + (f"  {comment}" if comment else ""))
            attributes_written.add(assignment["port"])
        else:
            rendered.append(line)

    missing = [item for item in assignments if item["port"] not in location_written]
    missing_attributes = [item for item in assignments if item["port"] not in attributes_written]
    if missing or missing_attributes:
        if rendered and rendered[-1]:
            rendered.append("")
        rendered.append(f"// Managed by gowin-mcp pin plan {plan_id}")
        for assignment in missing:
            rendered.append(f'IO_LOC "{assignment["port"]}" {assignment["pin"]};')
        for assignment in missing_attributes:
            rendered.append(
                f'IO_PORT "{assignment["port"]}" {_format_attributes(assignment["attributes"])};'
            )
    return newline.join(rendered) + newline


def gowin_apply_pin_plan(
    project_file: str,
    board_profile: str,
    requests: list[dict[str, Any]],
    expected_plan_id: str,
    constraint_file: str | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    project = _validate_project(project_file)
    plan = _plan_pins(project, board_profile, requests, constraint_file)
    if not re.fullmatch(r"[0-9a-f]{64}", expected_plan_id):
        raise ValueError("expected_plan_id must be a lowercase SHA-256 value from gowin_plan_pins")
    if plan["plan_id"] != expected_plan_id:
        raise ValueError("pin plan changed; run gowin_plan_pins again and review the new plan_id")
    cst_path = Path(plan["constraint_file"])
    current, encoding = _read_text(cst_path)
    updated = _render_cst(current, plan["assignments"], plan["plan_id"])
    diff = "".join(
        difflib.unified_diff(
            current.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=str(cst_path),
            tofile=str(cst_path),
        )
    )
    result = {**plan, "applied": False, "changed": current != updated, "diff": diff[:40000]}
    if not apply or current == updated:
        return result
    if not plan["apply_ready"]:
        raise ValueError("pin plan is not apply-ready: " + "; ".join(plan["blocking_reasons"]))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = cst_path.with_name(f"{cst_path.name}.bak-{stamp}")
    shutil.copy2(cst_path, backup)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding=encoding, newline="", dir=cst_path.parent, prefix=f".{cst_path.name}.", delete=False
        ) as handle:
            handle.write(updated)
            temporary = Path(handle.name)
        os.replace(temporary, cst_path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    result.update(
        {
            "applied": True,
            "backup_path": str(backup),
            "constraint_sha256_after": _sha256(cst_path),
        }
    )
    return result


def gowin_read_report(project_file: str, report_path: str, max_chars: int = 40000) -> dict[str, Any]:
    project = _validate_project(project_file)
    max_chars = int(max_chars)
    if not 1000 <= max_chars <= MAX_TOOL_TEXT:
        raise ValueError(f"max_chars must be between 1000 and {MAX_TOOL_TEXT}")
    requested = Path(report_path)
    report = requested.resolve() if requested.is_absolute() else (project.parent / requested).resolve()
    if not _is_within(report, project.parent.resolve()):
        raise PermissionError("report_path must stay inside the selected project")
    if report.suffix.lower() not in REPORT_SUFFIXES:
        raise ValueError(f"unsupported report type: {report.suffix}")
    if not report.is_file():
        raise FileNotFoundError(f"report not found: {report}")
    raw = report.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    return {
        "path": str(report),
        "bytes": len(raw),
        "truncated": len(text) > max_chars,
        "text": text[:max_chars],
    }


def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "gowin_start_build":
        return gowin_start_build(**arguments)
    if name == "gowin_build_status":
        return gowin_build_status(**arguments)
    if name == "gowin_diagnose_log":
        return gowin_diagnose_log(**arguments)
    if name == "gowin_environment":
        return gowin_environment()
    if name == "gowin_inspect_project":
        return gowin_inspect_project(**arguments)
    if name == "gowin_build_project":
        return gowin_build_project(**arguments)
    if name == "gowin_read_report":
        return gowin_read_report(**arguments)
    if name == "gowin_timing_summary":
        return gowin_timing_summary(**arguments)
    if name == "gowin_pin_audit":
        return gowin_pin_audit(**arguments)
    if name == "gowin_plan_pins":
        return gowin_plan_pins(**arguments)
    if name == "gowin_apply_pin_plan":
        return gowin_apply_pin_plan(**arguments)
    raise ValueError(f"unknown tool: {name}")


def _result(request_id: Any, value: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": value}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _tool_text(value: Any) -> str:
    # Keep MCP tool payloads ASCII on Windows pipes while preserving Unicode
    # semantics for callers that parse the embedded JSON text.
    return json.dumps(value, ensure_ascii=True, indent=2)


def handle_request(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    if method == "initialize":
        requested = message.get("params", {}).get("protocolVersion", "2024-11-05")
        return _result(
            request_id,
            {
                "protocolVersion": requested,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        return _result(request_id, {"tools": TOOLS})
    if method == "tools/call":
        params = message.get("params") or {}
        try:
            value = _call_tool(params.get("name", ""), params.get("arguments") or {})
            content = _tool_text(value)
            return _result(request_id, {"content": [{"type": "text", "text": content}], "isError": False})
        except Exception as error:  # MCP tool errors are returned as tool results.
            content = _tool_text({"error": str(error)})
            return _result(request_id, {"content": [{"type": "text", "text": content}], "isError": True})
    if method and method.startswith("notifications/"):
        return None
    return _error(request_id, -32601, f"Method not found: {method}")


def main() -> int:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=True, separators=(",", ":")) + "\n")
                sys.stdout.flush()
        except Exception as error:
            traceback.print_exc(file=sys.stderr)
            response = _error(None, -32603, f"Internal error: {error}")
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--build-worker":
        raise SystemExit(_build_worker(sys.argv[2], sys.argv[3]))
    raise SystemExit(main())
