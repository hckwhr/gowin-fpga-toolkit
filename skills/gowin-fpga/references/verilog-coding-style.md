# Verilog And SystemVerilog Coding Style For Gowin

Use this reference for synthesizable RTL. Testbench-only code may use broader
language features, but it must remain separate from synthesis sources.

## Source Priority

Apply rules in this order:

1. The current `.gprj` language mode, exact Gowin device, generated-IP
   ownership, and observed synthesis behavior.
2. Gowin's installed device and synthesis manuals.
3. The project-local style where it does not violate correctness or hardware
   safety.
4. The portable engineering rules below.

Do not silently convert `.v` sources to SystemVerilog or use constructs that
the selected Gowin project has not proved it accepts. For Verilog-2001 use
`always @*`, `reg`, and `wire`; for an enabled `.sv` flow prefer
`always_comb`, `always_ff`, and `logic`.

The keywords **must**, **should**, and **may** indicate correctness gates,
strong defaults, and optional choices respectively.

## Naming And Layout

- Preserve a coherent existing project convention. For a new standalone
  module, prefer one primary module per file, a matching file/module name, and
  descriptive `lower_snake_case` signal names.
- Name clocks and resets by function and domain. Active-low names end in `_n`;
  do not use that suffix for an active-high signal. Optional `_q`/`_d` or
  `_reg`/`_next` state suffixes must be used consistently within a module.
- Include units in names for frequency, time, sizes, and counts when ambiguity
  is possible, for example `clk_freq_hz` or `timeout_cycles`.
- Comments should record intent, protocol, polarity, units, cycle latency,
  safety behavior, and non-obvious hardware mapping. Do not narrate obvious
  syntax or leave stale commented-out implementations.
- Match the repository's indentation. Do not use tabs or trailing whitespace;
  keep declarations, port lists, and instances readable in ordinary diffs.

## Mandatory RTL Gates

### Processes And Assignments

- Clocked state **must** use nonblocking assignments (`<=`). Combinational
  processes **must** use blocking assignments (`=`). Never mix the two styles
  within one process.
- A synthesizable signal **must** have one procedural driver. Do not assign the
  same register from multiple `always` blocks or from both continuous and
  procedural assignments.
- Combinational logic **must** use `always @*` or `always_comb`, not a manually
  maintained sensitivity list. Prefer a continuous `assign` for a simple
  expression.
- Every combinational output **must** receive a value on every path. Put common
  defaults before conditional logic and include an explicit `default` in each
  `case`; unintended latches are build failures.
- Do not use `casex`, `full_case`, or `parallel_case`. Although an older Gowin
  guide mentions `full_case` as a latch escape, explicit complete assignments
  preserve simulation/synthesis equivalence and are the rule for new code.
  Use plain `case`; use `casez` only for a deliberate wildcard and document it.
- Synthesizable RTL **must not** contain `#` delays, event-control tricks, or
  simulation-only system tasks outside guarded assertion/debug code.

### Clocks, Resets, And Enables

- Prefer one real clock domain. Slow behavior **should** use a clock-enable
  pulse rather than a fabric-divided or gated clock.
- Do not create a clock with ordinary combinational logic. A required derived
  clock needs a supported Gowin clock resource, an explicit generated-clock
  constraint, and a CDC review.
- A clocked process sensitivity list **must** contain only its clock and, when
  required, one asynchronous reset/set signal. Other controls belong inside
  the process as synchronous enables or conditions.
- Reset polarity and synchronous/asynchronous behavior **must** follow the
  board and project contract. Name active-low signals with `_n`; do not import
  another project's reset convention merely for style consistency.
- If asynchronous reset assertion is required, deassert it synchronously in
  each destination clock domain unless the documented Gowin primitive and
  system reset architecture provide an equivalent guarantee.
- Reset control state and outputs that must enter a hardware-safe value. Avoid
  resetting every datapath register when doing so prevents BSRAM, shift-register,
  or DSP inference.
- SUG949 requires declared register initialization for its inference templates.
  When a register has both an HDL initial value and reset/set behavior, the
  values **must** agree. Confirm the generated hardware and startup behavior;
  an RTL initial value is not a substitute for a board reset requirement.

### Widths, Types, And Arithmetic

- Number literals and ports **must** have intentional widths. Do not rely on
  silent truncation, extension, or unsized decimal constants in datapaths.
- Signed values **must** be declared signed end to end. Cast mixed signed and
  unsigned operands explicitly, and size intermediate multiply, add, negate,
  and shift results before narrowing them.
- Port connections **must** match widths. Make deliberate extension,
  concatenation, slicing, or truncation visible at the connection.
- Compare a multi-bit value explicitly with zero instead of using it directly
  as a Boolean condition.
- Counter width calculations **must** handle zero- and one-count corner cases;
  parameterized `$clog2` expressions need a minimum width of one.
- Hand-written modules should reject implicit nets. When compatible with
  generated IP, place `` `default_nettype none`` before the module and restore
  `` `default_nettype wire`` after it so the directive does not leak into
  vendor sources.

### Hierarchy And Interfaces

- Keep the top level focused on physical I/O, board-safe output defaults,
  clock/reset distribution, and submodule connections. Keep reusable behavior
  in single-purpose modules.
- Use named port connections. Positional connections are acceptable only for a
  tiny, stable primitive whose documented interface makes mistakes unlikely.
- Bidirectional and tri-state behavior **must** terminate at a top-level I/O or
  an explicit Gowin I/O primitive. Internal `Z`-based muxing is forbidden.
- Parameters express external configurability; derived constants **should** be
  `localparam`. Label generate blocks and keep loop bounds elaboration-time
  constants.
- Do not edit generated IP internals. Change the owning configuration and
  regenerate, or wrap the generated module.

## State Machines

- Every FSM **must** have a valid reset/initial state, complete next-state
  behavior, and explicit recovery from illegal encodings.
- For new Gowin RTL, prefer separate state-register, next-state, and output
  logic when outputs are nontrivial. A two-process state-register plus combined
  decode/output form is also acceptable when defaults are complete and clearer.
- SystemVerilog may use an enum. Verilog-2001 should use named `localparam`
  encodings; never scatter numeric state literals through the logic.
- Treat Gowin's small-FSM binary/Gray and larger-FSM one-hot guidance as a
  starting heuristic, not proof. Choose encoding from synthesis resources,
  critical paths, upset-recovery requirements, and actual timing reports.
- Prefer registered or Moore-style outputs for glitch-sensitive board signals.
  A Mealy output needs an explicit reason and timing/glitch analysis.

## Clock-Domain Crossings

- Every crossing **must** identify source clock, destination clock, signal
  stability requirement, and transfer protocol.
- A slowly changing single-bit level should use a two- or three-flop
  synchronizer in the destination domain. A pulse needs a pulse synchronizer,
  toggle, or request/acknowledge handshake; it must not be assumed long enough.
- Do not synchronize a multi-bit bus bit by bit. Use a stable-data handshake,
  Gray-coded counter protocol, or asynchronous FIFO as appropriate.
- Reset release across domains is itself a CDC problem. Constraints and timing
  exceptions **must** describe the implemented synchronizer rather than hiding
  an unconstrained crossing.
- Preserve synchronizer structure from unrelated retiming or logic insertion,
  using verified Gowin attributes only when synthesis evidence shows they are
  needed.

## Gowin Resource Inference

- Pipeline long combinational paths when latency permits. Record the resulting
  cycle latency in the interface contract and test it.
- For BSRAM, SSRAM, FIFO, shift registers, and DSP, use the exact templates in
  installed SUG949 or a Gowin IP Core Generator instance when port behavior,
  read-during-write semantics, reset topology, or device mapping matters.
- Register memory and DSP outputs when the latency contract permits; this is a
  primary timing-closure lever on Gowin devices.
- After synthesis, verify the inferred primitive/resource type and count. A
  behaviorally correct simulation does not prove that BSRAM or DSP inference
  occurred.
- High-fanout enables and control nets require report evidence before adding
  `syn_maxfan` or replication attributes. Do not apply synthesis attributes as
  unexplained folklore.

## Review And Verification Gate

### Behavior contract before a nontrivial change

Reuse the project specification or stage note; do not require a new document
for every small edit. Record the affected ports and signed widths, clock/reset,
accepted transaction condition, cycle latency, initiation interval, sample/frame
deadline, ownership, and reset/flush/restart behavior. Describe numeric range,
rounding, saturation/wrap, and state persistence where relevant.

For a handshake, spell out the accepting edge and data stability under stall.
For a pipeline change, include a small cycle table when it clarifies alignment.
WaveDrom is optional; its absence must not block RTL work. Existing user choices
and project contracts suffice; ask only for a consequential unresolved choice.

Separate latency from throughput. A 32-lane generate loop does not prove 32
independent compute lanes, and a pipelined adder does not prove a sample deadline.
Check inferred DSP/RAM mapping, memory access ports, control fanout, recurrence
paths, and valid/data alignment against the actual report and testbench.

### Verification that can detect a wrong implementation

Derive expected results from the protocol, a preserved accepted implementation,
or an independently checked mathematical model. Do not just repeat the new RTL
algorithm in a checker. For arithmetic, exercise signed extrema, rounding,
overflow, saturation, and zero. For state/protocol changes, exercise stall,
reset during activity, flush, back-to-back events, and recovery as applicable.

Require actual compile/elaboration, a completed self-checking simulation, an
explicit terminal PASS, and no unexpected assertion/fatal/timeout. A testbench
scaffold, model review, lint PASS, or tool exit code alone is not simulation PASS.
Record seeds when randomized. Classify failures as RTL, testbench, environment,
timeout, or suspected tool defect before editing RTL. Preserve the first causal
error and focused expected/actual values. Do not weaken checks to obtain PASS.

For comment-only edits, compare non-comment tokens with the original immutable
baseline using the project's parser where available; formatting/AST checks do
not prove sequential equivalence. Do not mistake vendor interface stubs for
behavioral models. Unknown primitive semantics remain unresolved until the
exact Gowin IP model or manual establishes them.

Portable sources and the optimization loop are documented in
[report-driven-rtl.md](report-driven-rtl.md).

Before synthesis, review every changed RTL file for:

- language mode and source ownership;
- one driver per signal and assignment-type consistency;
- complete combinational assignments and no inferred latch;
- explicit widths, signedness, casts, counter bounds, and array indices;
- reset value, output-safe state, clock enable, and generated-clock intent;
- every CDC transfer and its protocol;
- legal top-level tri-states and intended RAM/DSP/FSM inference.

If `verible-verilog-lint` or another project-approved linter is installed, run
it before Gowin synthesis and review waivers individually. Do not install a
linter or mass-autofix sources merely because this reference mentions one.
Formatting success is not semantic validation.

After synthesis, treat latch inference, multiple drivers, implicit nets,
width/sign truncation, combinational loops, unconnected ports, removed intended
logic, failed RAM/DSP mapping, and unexpected clocks as actionable. Then run
place-and-route, `gowin_timing_summary`, and `gowin_pin_audit` on fresh reports.
For nontrivial state/protocol logic, add focused simulation when a compatible
simulator is actually available.

## Resolved Source Differences

- lowRISC mandates active-low asynchronous reset for its own projects. This
  Skill keeps reset style project- and hardware-specific because Gowin supports
  synchronous/asynchronous set/reset and existing boards differ.
- Gowin SUG113 recommends a three-process FSM; lowRISC standardizes a
  two-process FSM. Both are accepted here when state, decode, outputs, defaults,
  and illegal-state recovery remain explicit.
- SUG113 mentions `full_case`; portable guidance rejects it because it can hide
  RTL/synthesis mismatches. Explicit defaults take precedence.
- lowRISC prefers SystemVerilog constructs. Gowin project language mode takes
  precedence, so Verilog-2001 equivalents remain first-class.

## Sources

- Gowin `SUG113-1.3`, *Gowin 器件设计优化与分析用户指南*, chapter 2,
  available in the matching Gowin EDA documentation installation.
- Gowin `SUG949-2.2`, *Gowin HDL 编码风格用户指南*, especially chapters
  3 and 7-11, available in the matching Gowin EDA documentation installation.
- lowRISC, *Verilog Coding Style Guide*, pinned at commit
  `9c15ff5dce23eef969e00ab3715153967419eadd`:
  <https://github.com/lowRISC/style-guides/blob/9c15ff5dce23eef969e00ab3715153967419eadd/VerilogCodingStyle.md>.
- Chips Alliance, *Verible SystemVerilog Style Linter*, pinned at commit
  `c1d8f5e8be4105726ce09b01de14ff0716f303bf`:
  <https://github.com/chipsalliance/verible/blob/c1d8f5e8be4105726ce09b01de14ff0716f303bf/verible/verilog/tools/lint/README.md>.

External sources were checked on 2026-09-21. The two Gowin manuals and actual
GowinSynthesis reports remain authoritative for device-specific inference.
