# Debug, Robustness and Delivery

These independently written methods were informed by mixed audio/video FPGA
course examples. Source course files and personal contest solutions are not
distributed. Gowin device/tool documentation remains authoritative.

## Isolate a testable cause

For a substantial experiment, record what changed, what stayed identical and
what each possible result would rule out. Preserve the accepted baseline and
failed reports. Small RTL edits can substantially change placement and fanout;
do not infer timing improvement from line count or synthesis resources alone.

A bypass must actually block the original producer and ignore its responses.
Count real accepted transactions. A testbench that forces an internal signal
bypasses its driving logic; cover that logic separately and retain a top-level
pin-to-output test. Do not confuse a diagnostic parameter with proven isolation.

When output is wrong, narrow the chain from the physical interface inward:
output-domain pattern, adapter, synthetic stream, CDC, individual source, then
the complete design. The first failing boundary identifies the next useful test.

## Recovery and startup

Define deadlines and bounded recovery for external transactions that must
complete. Keep last-good data only where the product contract permits it.
Expose errors and count actual delivered samples/events, not merely announced
lengths. Preserve proven drivers where a small interface adapter is sufficient.

Use the project's reset architecture. If reset assertion is asynchronous,
deassert synchronously in each domain. Only PLLs that a domain depends on
should govern that domain's readiness. Start consumers and buffers before
unmuting sources; test reset during activity and cold startup.

## Timing exceptions and reporting

An infrequent control change alone never justifies an exception. Explain the
synchronizer, handshake, quiet phase or CE edge relationship, use the narrowest
correct endpoints and check the effective constraint and hold analysis.
Consult [contract-verification.md](contract-verification.md).

Gowin SUG940-2.0.4 documents these optional report commands:

```sdc
report_timing -setup -max_paths 200 -max_common_paths 1
report_high_fanout_nets -max_nets 50 -min_fanout 30
report_route_congestion -max_grids 50
```

The commands were accepted in an earlier V1.9.12.03 smoke build. Check support
in the active version; a report-setting change is not proof that a large
design's placement will remain identical. The MCP exposes printed setup path
clusters, fanout and congestion tables when present. Printed paths are a
subset, not the complete population of violating paths.

Do not import another vendor's `rename_clock`, `-datapath_only`, uncertainty,
PLL settings or download commands without checking Gowin support and meaning.
Do not add fanout attributes or run random placement variants to hide a
structural issue. Make further builds answer a specific remaining question.

## Delivery evidence

Distinguish simulation, decoded output, individual hardware observations,
mode transitions and endurance testing. A status LED proves control activity,
not correct samples. A successful soak proves only the tested duration,
conditions and coverage, never universal stability.

Choose repeatable tests suited to the product: rapid inputs, source changes,
external disconnects, warm operation and cold starts from the programmed image.
Record actual counts and conditions. For a demonstration, map each requirement
to implementation evidence and a visible action, and claim only what the
production path produces. Cycle-exact RTL exercises should specify sampling
edges, pulse duration and terminal count behavior before implementation.
