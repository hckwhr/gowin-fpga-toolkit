# Gowin Tcl and MCP

## Installation and configuration

The companion `gowin-fpga-toolkit` repository contains `gowin-mcp/server.py`.
Its root README provides Codex TOML and generic stdio MCP JSON examples.
The skill can also be used independently with the project's existing CLI.

The Windows build adapter uses paths relative to `GOWIN_HOME`:

- `IDE/bin/gw_sh.exe` for fixed Tcl builds;
- `IDE/bin/gw_ide.exe` for the vendor GUI;
- `Programmer/bin/programmer_cli.exe` is checked for presence only.

MCP 0.5.1 requires an absolute `GOWIN_HOME` and explicit semicolon-separated
absolute `GOWIN_ALLOWED_ROOTS`. Missing configuration fails closed. Use narrow
project roots and include a board-profile directory only if needed. Restart
the client/server after configuration changes. Windows EDA V1.9.12.03 is the
tested integration; other versions need their own smoke build.

## Fixed build path

SUG1220 documents running a Tcl script through `gw_sh.exe`. For a project-specific
CLI fallback, use the installed executable and an ASCII-path script such as:

```tcl
open_project {C:/fpga/workspace/example/example.gprj}
run all
run close
```

Save stdout/stderr and inspect fresh outputs. Project-specific constraints and
settings still apply. Do not introduce arbitrary shell or Tcl endpoints to MCP.

## Tools

| Tool | Purpose |
|---|---|
| `gowin_environment` | Check configured paths, without hardware access |
| `gowin_inspect_project` | Inspect device, enabled files and missing inputs |
| `gowin_start_build` | Start a persistent fixed build and return its ID |
| `gowin_build_status` | Read receipt, heartbeat, log and outputs by ID |
| `gowin_build_project` | Compatibility wait for the same persistent build |
| `gowin_diagnose_log` | Read exact error/warning counts and literal progress markers |
| `gowin_read_report` | Read bounded project-local text reports |
| `gowin_timing_summary` | Summarize fresh STA and clock-constraint coverage |
| `gowin_pin_audit` | Compare CST with the final pin report |
| `gowin_plan_pins` | Plan from a device/revision-specific profile |
| `gowin_apply_pin_plan` | Preview or apply the unchanged plan with a CST backup |

No device scan, programming, erase, OTP, key or security operation is exposed.
Project files and the toolchain must be trusted; root restrictions are not a
sandbox for arbitrary vendor projects or external source includes.

## Persistent builds and evidence

Prefer `gowin_start_build` and poll `gowin_build_status` with the returned ID.
Receipts, logs and archived text reports live under
`<project>/.gowin-mcp/<build_id>/`. A separate worker survives client disconnects.
One lock prevents concurrent managed builds in a project directory. External
GUI/CLI builds are outside that lock; check them before launching another build.

`budget_seconds` warns only. The compatibility call's `timeout_seconds` bounds
waiting, never EDA lifetime; keep polling the existing ID after a timeout. A
stale heartbeat means unknown status, not a dead router. A responsive supervisor
does not prove routing progress. Never remove a lock or restart just for silence.

Optional `place_option` (0–4) and `route_option` (0–2) are bounded integers,
not Tcl. Use project-proven settings when available. They are disallowed for
`stage="syn"`. The worker checks actual values against `impl/pnr/cmd.do` and
archives fresh text reports per build ID. Large binary outputs are hashed in
place; subsequent builds can make old receipts stale without erasing archives.

`success=true` establishes fresh outputs, normal exit, no logged errors,
unchanged tracked inputs and matching requested options. It is not timing or
hardware acceptance. See [contract-verification.md](contract-verification.md)
for `.p`/`.pr`/STA/bitstream requirements and missing-data semantics. Track
implicitly included external inputs separately when outside the fingerprint.

## Pins

Use an exact device/revision profile and explicit port requests to generate a
content-bound `plan_id`. Applying recomputes the plan, rejects a changed ID,
backs up the CST and replaces it atomically. Preview is the default. Inspect
the source schematic and bank voltage yourself: the server validates profile
consistency but does not verify the truth of its evidence strings. Rebuild
and audit the final pin report before hardware use.
