# Gowin Development Workflow

## Project Intake

Inspect the `.gprj` as XML. Record the `Device` name, full `pn`, device ID,
enabled files, and missing files. Check whether generated IP files and their
configuration sources are both present. Do not edit `impl` output as source.

Declare the top module explicitly. A blank source, unresolved hierarchy, or
missing constraint blocks implementation.

## Hardware And Constraint Lock

Before CST/SDC edits, establish:

- exact board/SOM/Dock revision and FPGA B/C version;
- primary oscillator pin and frequency;
- reset polarity and safe output state;
- every used port's package pin, bank voltage, I/O standard, pull, and drive;
- reserved configuration, JTAG, DDR, SerDes, and board-peripheral pins;
- each clock and generated clock with its source and intended frequency.

Top-level HDL names and CST port names must match exactly. Keep only interfaces
used by the design. A copied full-board CST is not a pin plan.

## HDL And IP Changes

- Keep one real clock domain until requirements justify another.
- Use clock enables for slow logic instead of fabric-divided clocks unless the
  clocking design explicitly requires and constrains a generated clock.
- Synchronize asynchronous inputs and crossings; debounce mechanical inputs.
- Reset outputs to a board-safe state, especially power-amplifier enables.
- Bound counters and derive widths from the verified clock and interval.
- Preserve generated Gowin IP wrappers. Change the owning IPC/configuration and
  regenerate rather than hand-editing generated internals.
- Add a focused simulation or lint check for non-trivial protocol/state logic
  when an installed simulator supports the exact source.

## Build Gate

Build in order: RTL parse/hierarchy, synthesis, constraints, place-and-route,
timing, then bitstream. For each failure, preserve the first decisive error and
change one cause.

After synthesis inspect top, removed logic, inferred latches, multiple drivers,
unconnected ports, and resource mapping. After place-and-route inspect:

- implementation success and resource limits;
- timing slack for every constrained clock;
- unconstrained paths or missing clocks;
- final Ports & Pins against the locked pin table;
- the timestamp and path of the newly generated `.fs`.

Use `gowin_timing_summary` for structured STA evidence. A passing analyzed
constraint set is not timing-clean when the report is stale or
`clocks_without_explicit_sdc` is non-empty. Use `gowin_pin_audit` to compare the
active CST with the final Pin Report and expose auto-assigned ports, duplicate
locations, part mismatches, and stale pin evidence.

For pin automation, create a project/allowed-root board profile following the
MCP `board-profile.schema.json`. It must name the exact board revision, exact
device name (including B/C), part number, evidence sources, usable pins,
reserved pins, roles, Bank voltage, and IO type. Preview with
`gowin_plan_pins`; apply only the same plan through `gowin_apply_pin_plan` with
its `plan_id`, then rebuild and audit again. Missing or uncertain board
evidence blocks CST mutation.

A process icon, exit code, or pre-existing `.fs` is insufficient by itself.

For nontrivial optimization, use the experiment and build-monitoring rules in
[report-driven-rtl.md](report-driven-rtl.md). Run focused simulation and synthesis
first; inspect removed logic, resource growth and critical-path evidence before
spending time on P&R. This staging saves rejected experiments; it does not waive
full regression, routed timing, or pins for the final candidate.

Prefer `gowin_start_build` plus `gowin_build_status` for long builds. A quiet log
is not a hang diagnosis. Preserve the current build until it completes or there
is specific evidence supporting interruption. A timeout/budget warning is not
permission to restart, loosen SDC, reduce required parallelism, or lower a gate.

## Evidence Levels

| Level | Minimum evidence | Allowed claim |
|---|---|---|
| `inspected` | project/device/source/constraint inventory | static project state is known |
| `rtl-checked` | successful hierarchy/RTL parse | HDL parses for the selected top |
| `synthesized` | fresh synthesis report with zero errors | synthesis completed |
| `routed` | fresh P&R plus timing/ports reports | implementation completed with stated timing status |
| `bitstream-generated` | fresh `.fs` tied to this build | configuration image was generated |
| `programmed` | exact device/cable/image/operation success log | image was written to the stated target |
| `observed` | named behavior and conditions on hardware | only the observed function passed |

Never promote a claim automatically. In particular, `bitstream-generated` does
not prove programming, boot, signal integrity, or functional behavior.

## Programmer Boundary

The local MCP does not expose Programmer. Follow the active project's verified
programming profile and the user's selected persistent/volatile mode. Reuse
existing authorization when the user requests programming; do not add a new
SRAM trial or repeated confirmation to an already authorized permanent-Flash
workflow. Match scanned device/cable and accepted image, retain command/log
evidence, and verify power-cycle behavior separately. OTP, keys, security bits,
or unrelated erase/address changes are separate actions outside ordinary
programming authorization.
