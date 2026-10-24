---
name: gowin-fpga
description: Write and review Verilog/SystemVerilog for Gowin FPGA projects, inspect .gprj files, constrain clocks and pins, run Gowin EDA builds, and troubleshoot RTL, CDC, timing and resource inference. Use for Gowin or Tang FPGA work; not unrelated MCU firmware or other vendors' toolchains.
---

# Gowin FPGA

Use the exact board, device, package, tool version, source tree, constraints,
and reports from the current project. A tutorial that builds for another board
is process evidence only, never pin or device evidence.

## Start Receipt

Record before changing HDL or constraints:

- board and revision, or `unknown`;
- exact device/part number from `.gprj`, silicon scan, or board evidence;
- Gowin EDA version and project path;
- intended clock, reset, interfaces, and observable acceptance result;
- current evidence: `inspected`, `rtl-checked`, `synthesized`, `routed`,
  `bitstream-generated`, `programmed`, or `observed`;
- selected references and whether hardware access is requested.

Stop at inspection when the board revision, part number, clock, bank voltage,
or target project is unresolved and the requested change depends on it.

## Read By Need

- Read [references/local-materials.md](references/local-materials.md) to select
  the relevant local note, official manual, example, or extracted schematic.
- Read [references/development-workflow.md](references/development-workflow.md)
  before changing HDL, CST/SDC, IP configuration, or build settings.
- Read [references/verilog-coding-style.md](references/verilog-coding-style.md)
  before writing, refactoring, or reviewing synthesizable Verilog/SystemVerilog.
  Apply its mandatory RTL and CDC gates, then use the Gowin-specific inference
  rules only where the selected device and synthesis report support them.
- Read [references/tcl-and-mcp.md](references/tcl-and-mcp.md) when using
  `gw_sh`, the local `gowin` MCP server, or a direct CLI fallback.
- Read [references/contract-verification.md](references/contract-verification.md)
  when changing event ownership, shared arithmetic, synchronous RAM latency,
  runtime settings, self-checking testbenches, CE timing exceptions, or build
  completion checks. It supplements the existing workflow with edge-specific
  contracts and distinguishes missing evidence from a passing result.
- Read [references/report-driven-rtl.md](references/report-driven-rtl.md) for
  throughput/resource/timing optimization, generated RTL review, or long builds.
  It adapts report-driven experiments and contract-based verification from the
  reviewed Ross and Eriemon projects; vendor commands remain Gowin-specific.
- Read [references/debug-and-delivery-discipline.md](references/debug-and-delivery-discipline.md)
  when isolating a board or timing fault, planning an experiment, adding error
  recovery, extending SDC reports, or preparing contest acceptance and defence.
  Its methods come from an Anlogic course; every tool and constraint detail in
  it is Gowin's own and names its evidence.

Do not bulk-load all manuals. Open the board schematic and the one device/tool
manual that answers the current question.

## Device And Board Gate

Do not infer a board from a family name. Match the exact FPGA device, package,
speed grade, SOM/Dock revision, oscillator and bank supplies to the project.
Never transfer a CST, IP configuration or Programmer operation between boards
without direct evidence, including B/C device variants of the same family.

The companion toolkit includes a low-speed example profile for Tang Mega 138K,
SOM 30354 + Dock 31005, GW5AST-138C. It is optional and does not select a board
for the user. Verify its listed source documents and actual wiring before use;
other revisions require their own evidence and profiles.

## Cross-Vendor Reference Gate

When a user provides Anlogic/ALINX or another vendor's example, use it only as
structural or algorithmic evidence. Before adapting it, re-lock the exact
Gowin part, board revision, clock/reset contract, I/O bank voltage, pins,
constraints, and Programmer target for the current project.

- Do not copy vendor primitives, generated PLL/IP wrappers, device files,
  constraint syntax, or Programmer operations across vendors.
- Re-implement the portable behavior with supported Gowin primitives or plain
  RTL, regenerate Gowin IP in the target EDA, and translate CST/SDC constraints
  from first-party evidence.
- After migration, run the normal Gowin synthesis, P&R, timing, pin, and
  bitstream gates. Record the source vendor and the parts that were deliberately
  not reused.

Read [references/cross-vendor-porting.md](references/cross-vendor-porting.md)
when the reference project comes from another FPGA vendor.

## Execution

1. Inspect `.gprj`, enabled files, device, missing paths, and existing reports.
2. Lock top module, primary clocks, resets, pins, I/O standards, and generated
   IP ownership before editing behavior.
3. Make the smallest coherent HDL/constraint change. Follow the RTL language
   mode and coding gate in `references/verilog-coding-style.md`. Preserve
   generated IP wrappers and regenerate IP when its owning configuration changes.
4. Run synthesis, then place-and-route. Use `gowin_timing_summary` and
   `gowin_pin_audit` on fresh reports; read the first real error and do not
   infer success from an exit code alone.
5. Treat a fresh `.fs` as `bitstream-generated`, not as hardware proof.
6. Program SRAM or Flash only when the user requests hardware mutation and the
   exact board, cable, device, image, operation, and rollback/recovery path are
   known. Verify behavior separately.

Prefer the local `gowin` MCP tools when exposed. They intentionally stop before
hardware programming. Use the documented CLI fallback when MCP is unavailable.

For automatic pin work, require an evidence-backed board profile with the exact
revision and project part number. Run `gowin_plan_pins`, review its evidence and
assignments, then pass the unchanged `plan_id` to `gowin_apply_pin_plan`. Never
let the FPGA placer guess external board wiring or apply a profile with an
unknown revision.

## Closeout

Report the project and device, changed files, command/tool used, decisive report
lines, fresh artifacts, achieved evidence level, and anything not verified.
Historical `.fs` files and reports inside course ZIPs remain examples only.

## Anlogic System Design Pattern Gate

When a Gowin task involves mixed audio/video pipelines, menus, source switching, waveform display, multi-clock control, frame buffers, or porting ideas from the Anlogic reference set, read [references/anlogic-system-design-patterns.md](references/anlogic-system-design-patterns.md) before editing RTL.

Apply the reference as an architecture and verification guide only. Re-derive Gowin clocks, memories, FIFOs, device primitives, I/O standards, constraints, and programming flow from the active project and Gowin documentation. Prefer contract-first interfaces, transactional CDC, frame-boundary visual commits, explicit buffer ownership, click-free audio transitions, and self-tests that use the production data path.
