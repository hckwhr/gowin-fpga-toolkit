# Transaction and Evidence Checks for Gowin

Use this reference for the changed path only. Preserve the project's language,
interfaces, tests, constraints and accepted hardware baseline. It adds checks
to the existing workflow; it does not install the supplied package's routing,
directory conventions, mandatory forms or retry rules.

## Define the Real Acceptance Edge

- Trace production callers and consumers before changing a module. Define
  acceptance at the active clock edge, including reset, CE and ready/valid.
  If the interface specifies CE-qualified acceptance, the producer and consumer
  must agree on `ce && valid && ready`; do not assume this for other protocols.
- Under backpressure keep the offered payload and all ownership metadata stable
  until accepted, unless the interface explicitly defines cancellation. No loss,
  duplication or replay; test stalls at the boundary rather than only steady state.
- For delayed results, carry lane/index, event ID and any required ownership
  generation alongside valid. A stolen/reassigned voice or a reset must reject
  an old owner's in-flight result. Test two starts at the same pitch and an OFF
  arriving after reassignment, plus release before a queued ON is accepted.
- State when dynamic settings commit (event, sample or frame boundary). Test
  changes just before and after that boundary, including buffered transactions.
  Preserve existing immediate-versus-deferred semantics unless asked to change them.

## Memory and Shared Arithmetic

For asynchronous-to-synchronous RAM conversion, account for registered read
latency at every consumer, including the first and last byte, empty/full buffer,
line terminator, stalls and read-during-write behavior. Present the next address
early enough; do not shift valid or metadata independently of the data. Use the
project's tested synchronous-read pattern and verify actual BSRAM/SSRAM mapping
in synthesis; an RTL attribute or estimate is not a measured saving.

When sharing an operator, preserve independent oscillator/voice state. Derive
the worst fill time from lane scan plus pipeline and arbitration delays. State
the legal sample interval and why the production source guarantees it. Compare
against a frozen reference at that interval, with changing inputs and ownership.
Add a negative test below the minimum interval that detects the promised failure
(assertion, rejection or reference divergence, as specified). A test which still
passes when the timing contract is violated does not demonstrate that bound.

## Self-Checking Simulation

- Compile with the production HDL language mode and real file/include list.
  Enabling SystemVerilog solely to hide a Verilog-2001 incompatibility is not a fix.
  Syntax/elaboration success alone is not a simulation pass.
- Avoid testbench races: drive synchronous inputs away from the sampling edge
  (for example on the falling edge), or use a supported clocking block. Capture
  pre-edge handshake values for acceptance and check registered outputs after
  nonblocking updates. Do not withdraw valid based on ready in the DUT's active
  event region. Match the project's time resolution if using a settling delay.
- Compare value, cycle, lane and ID where applicable. On the first mismatch print
  expected/actual values and the accepted input transaction. Distinguish reference,
  stimulus/scoreboard, RTL, reset/init and language/tool errors before editing RTL.
- Timeout, mismatch and unexpected X/Z must fail the process (`$fatal` when
  supported, otherwise the harness must reject them). Require a terminal PASS;
  neither an early `$finish` nor a zero compiler exit is sufficient.
- Keep existing regression cases. For external-input bugs, include a production
  top-level test from pin levels through debounce/ADC decoding to decoded output.
  Direct event-bus stimulus alone cannot detect an unused input port or a
  constant overriding the route. For audio, verify actual output frames/samples;
  an internal active flag does not prove audible output.

Review technical examples before adopting them. For known binary data, reduction
XOR is the appended even-parity bit; its complement gives odd parity. Reduction
AND does not detect one-hot. A nonzero value with `v & (v-1)` equal to zero has one
set bit, with width and X/Z treatment specified. Variable shifts are legal RTL;
their hardware cost and bounds require measurement, not a blanket ban.

## Timing Exceptions Require Edge Proof

A control bit changing infrequently is not sufficient for a false path,
multicycle or relaxed max delay. Prove when the destination can first use the
new value, and what synchronizer/handshake, quiet phase or commit protocol
guarantees that edge relationship. Otherwise retain the normal timing check.

For common-CE multicycle paths, prove both launch and capture qualification,
including nested conditions and reset/bypass paths. Pair setup and hold using
the tool's actual edge semantics. Verify matched endpoints and active constraints
in the generated timing report, and check hold again. Do not broaden a wildcard
over mixed full-speed/CE state to remove a violation.

Reuse saved Tcl object collections or a verified compressed SDC only when the
installed Gowin version supports it and the matched objects remain identical.
Do not claim build-time improvement without a measured comparison, or introduce
`syn_maxfan` as a generic answer to routing-dominated delay.

## Build Completion and Evidence

The local MCP 0.5 reports `log.last_stage` with the literal source line and
`log.unrouted_nets` with its evidence. An absent count is unknown. Neither a quiet
log nor a live worker heartbeat proves tool progress or a hang.

For the current Gowin flow, `.p` is placement output, `.pr` is routed output,
`*_tr_content.html` contains STA, and `.fs` is the bitstream. `.tr.html` can be
only a wrapper. A PR0004 line reporting zero unrouted nets does not override the
tool's error exit or establish that finalization completed.

MCP 0.5's terminal `stage_outputs` and `missing_outputs` inventory nonempty fresh
outputs. For P&R/all, route, full timing, pin report and bitstream are required
in addition to normal exit, no errors and matching inputs/options. Synthesis
requires its fresh report. This is build completion, not timing or board acceptance.
Reports are archived per build ID; large `.p`, `.pr` and `.fs` files are hashed
in place rather than duplicated into the report archive.

Missing timing counters/slacks remain unknown (`null`); a partial report cannot
claim timing met. Use fresh complete STA plus pin/clock audits and the project's
actual setup/hold gates before programming. Reserve hardware-verified claims
for observed board behavior. Never restart, terminate or remove a build lock
automatically because diagnostics are incomplete.

## Adaptation Sources

These independently written checks consolidate contract, waveform planning,
RTL build, testbench and simulation-review methods for a Gowin workflow.
Reference packages and vendor source code are not redistributed. Incorrect
one-hot/parity/shift examples and foreign constraint syntax were not adopted.
Gowin manuals, active project code and actual reports remain authoritative.
