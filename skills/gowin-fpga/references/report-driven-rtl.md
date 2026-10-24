# Contract and report driven RTL development

Use for timing, throughput, resource optimization and substantial RTL changes.
This is a portable adaptation of the sources below, not an AMD tool workflow.

## Baseline and one testable hypothesis

Identify an accepted source snapshot, exact tool/part/clock settings and the
target metric. Separate functional correctness, cycle latency, initiation
interval, sample deadline, parallel lane count, and physical timing slack.
Record measured values rather than estimates when calling a baseline accepted.
Keep unknown/unrun/incomplete distinct from pass or fail.

Before a long build, state the suspected limiting path and expected change.
Example: register the signed sum to split an add/compare/mux chain, while valid
and data still settle before the existing audio sampling edge. Check reset,
retune and ownership transitions where the old pipeline can contain stale data.

Choose a coherent change whose effect can be attributed. Review:

- feedback dependence and carry/compare depth;
- memory ports, access pattern, banking, and read/write semantics;
- fanout and physical routing pressure from broadcast controls;
- latency alignment, channel rate mismatch, FIFO depth and backpressure;
- fixed-point range, intermediate widths, rounding and saturation;
- intended parallelism versus synthesis folding/sharing.

HLS II analysis informs the questions, but Gowin RTL does not accept Vitis HLS
pragmas, ap_fixed libraries, XPM primitives, or Vivado XDC/tool commands directly.
Physical reports and the target Gowin manuals decide inference and timing.

## Spend build time on informative candidates

Use existing lint/elaboration and a focused self-checking test first, then
synthesis to inspect resource/mapping and structural warnings. Run P&R when
those results justify testing the physical hypothesis. A synthesis estimate
cannot prove post-route timing; a functional addition may merit P&R even when
it intentionally uses more resources or adds specified latency.

For final delivery, run the applicable full regression and fresh routed timing
and pin audits. Tie source/configuration hashes, reports and bitstream together.
Do not apply an arbitrary universal 10% gain threshold, three-operation logic
limit, or 60% resource cutoff. Use the project's acceptance criteria and actual
critical paths. Never weaken constraints or drop required lanes to get PASS.

For each substantial attempt retain a compact record:
source identifier; hypothesis; changed files; command/tool version; test result;
resource counts; worst setup/hold; relevant path endpoints; build duration;
decision (accept/reject/incomplete); next explanation to test.
Use existing stage notes or JSON records; a forced commit per experiment is
unnecessary. Preserve failures before reverting and never overwrite user edits.
If repeated attempts bring no new evidence, revisit the architecture rather
than repeating the same build or adjusting random implementation switches.

## Observe long builds without losing work

The Gowin MCP 0.3 build-start call returns an ID immediately; status reads a
durable receipt, heartbeat, log age, elapsed time, last vendor progress marker,
first error and grouped message counts. Log silence and heartbeat are separate:
a live supervisor does not prove router progress, and a stale supervisor does
not prove the child is dead. Treat stale heartbeat as unknown and investigate.

One managed build owns a project directory at a time. After an MCP restart,
read the saved receipt instead of creating another build. A stale lock is not
automatically removed. Check the recorded process and preserve the attempt
before manual recovery. Direct CLI builds are outside this ownership lock;
inspect them before starting another build in the same directory.

Budgets warn, not kill. The compatibility blocking call returns the build ID
when its wait expires; poll it later. Do not interrupt merely because a vendor
phase has not printed output recently. Distinguish manual stop, tool error,
unknown status, completed implementation with bad timing, and accepted image.

Diagnostics retain exact raw line references and total counts even when message
display is capped. Source inspection findings are separate from tool-reported
warnings. Missing/empty reports do not mean zero violations. Logs and existing
artifacts alone cannot establish live process state or source equivalence.

## Source and adoption limits

Reviewed 2026-10-05 at these commits:

- AMD/Xilinx Ross, MIT, `2cdc9eef1b6b5b17fa45f5e4d468e5483a1c92de`:
  <https://github.com/Xilinx/ross-ai-assistant>.
  `skills/vivado-simulate-rtl/SKILL.md`: terminal simulation verdict and failure
  classification; `skills/vivado-rtl-lint/parse_lint_report.py`: format-aware
  diagnostics; `skills/hls-optimize/SKILL.md`: hypotheses and measured outcomes;
  `docs/reference/vivado-mcp-tools.md`: long execution separated from monitoring.
  The repository documents the Vivado MCP; it is not the server source package.
- Eriemon Verilog Generator, Apache-2.0,
  `007372fb63fe1d0b51e5bb10f4569d0b62ae6730`:
  <https://github.com/Eriemon/verilog-generator>.
  `scripts/python/existing_rtl/semantic_contract.py`: deterministic vectors and
  semantic checkpoints; `references/workflows/workflow-contracts.md`: run
  provenance and distinct evidence states.
- Eriemon HLS Generator, Apache-2.0,
  `8a22caae4bdc1b5bb6191ef1ed82b63e92d1280a`:
  <https://github.com/Eriemon/hls-generator>.
  `scripts/python/validation/stage_verifier.py`: interface/vector drift;
  `references/hls-report-driven-optimization.md`,
  `hls-task-parallel-strategy.md`, `hls-modeling-strategy.md`: bottlenecks,
  channel ownership/restart and explicit numeric intent.

The two Eriemon projects identify Jiyuan Liu, He Li and Southeast University
HIQC as authors; they are not AMD official repositories. These local rules and
MCP additions are independently written adaptations of methods, not copies of
their runtimes. No hosted document service, remote SSH dependency, mandatory
renderer, model provider or installer is introduced.
