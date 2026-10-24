# Anlogic Mixed Audio/Video System Design Patterns

> Purpose: extract reusable architecture patterns from the Anlogic reference projects for Gowin FPGA work. This is a behavioral design reference, not a source of vendor primitives, pin constraints, clock settings, or programming procedures.
>
> Reviewed and consolidated: 2026-09-29.

## 1. Evidence and portability boundary

Use the following evidence order:

1. Current project RTL, board schematic, pin report, timing report, and measured waveforms.
2. Gowin device manuals, IP configuration, constraints, and programmer documentation.
3. Cross-vendor examples only for architecture, protocols, state machines, buffering, and verification ideas.

Portable concepts:

- module contracts and handshake semantics;
- control-plane/data-plane separation;
- clock-domain crossing transactions;
- frame-atomic UI updates;
- buffering and ownership rules;
- fade/crossfade policies;
- error detection and self-test paths;
- staged bring-up and evidence collection.

Do not copy without re-derivation:

- PLL/MMCM configuration and generated clocks;
- RAM/FIFO/DDR/video/audio vendor primitives;
- reset macros or device-specific startup logic;
- pin names, I/O standards, clock constraints, false paths, or programmer commands;
- assumptions about BRAM read latency, FIFO flags, DSP widths, or signed arithmetic.

## 2. Contract-first data paths

### 2.1 Unified PCM stream

All audio producers and consumers should meet the same sample contract:

- pcm_valid: producer presents a complete stereo sample;
- pcm_ready: consumer can accept the sample;
- pcm_left, pcm_right: signed fixed-width samples;
- transfer occurs only when pcm_valid and pcm_ready are both asserted;
- while valid is asserted and ready is deasserted, sample data and associated metadata remain stable.

Recommended assertion or synthesizable monitor:

- remember the stalled sample;
- if data changes before acceptance, set a sticky contract_error flag;
- expose the flag on a debug page, test point, or status register.

This contract lets real-time synthesis, a test tone, stored PCM, and future sequencer playback share one serializer and one verification path.

### 2.2 Adapter at every incompatible edge

If an existing block emits an enable pulse, FIFO read request, or serializer-specific strobe, put the mismatch in a small adapter. Do not spread serializer timing assumptions into every sound source.

An adapter should own:

- rate conversion between local sample_tick and stream handshake;
- sample holding during backpressure;
- width/sign conversion;
- underflow/overflow reporting;
- reset behavior and first-sample behavior.

## 3. Source selection without hidden consumption

A source multiplexer must route ready only to the selected source. Unselected sources must not pop a FIFO, advance a score, or consume an event.

For source changes:

1. fade the active source down;
2. switch ownership at zero or near-zero gain;
3. reset or explicitly preserve the new source state;
4. fade the new source up;
5. report the committed source, not merely the requested source.

Use the same mechanism for live synthesis, diagnostic tones, offline playback, and demo sequences.

## 4. Separate control plane from data plane

Buttons and menus should publish parameter events; they should not reach into oscillator, mixer, LCD raster, or serializer internals.

Recommended partition:

- input plane: debounce, edge detection, long/short press, repeat, and future ADC normalization;
- control plane: mode state machine, parameter limits, menu focus, note mapping, and voice allocation commands;
- audio data plane: oscillator, envelope, timbre, mixer, effects, PCM contract, and output adapter;
- video data plane: frame timing, OSD composition, waveform snapshot, and LCD pins;
- observability plane: sticky errors, counters, active state, latency markers, and self-test selection.

Keep key-debounce modules generic. They should output stable level and edge pulses only.

## 5. Clock-domain crossing as transactions

### 5.1 Single-bit levels

Use a two-flop synchronizer for a slowly changing single-bit level. Do not treat the synchronized level as a one-cycle event unless the destination performs edge detection.

### 5.2 Event or command transfer

Use a request/acknowledge toggle for infrequent commands crossing unrelated clocks:

1. source writes the payload into a holding register;
2. source toggles req_toggle;
3. destination synchronizes the toggle and detects change;
4. destination captures the stable payload and toggles ack_toggle;
5. source may issue the next command only after the acknowledge returns.

This prevents missing narrow pulses and prevents a new payload from overwriting an unconsumed one.

### 5.3 Multi-bit quasi-static bundles

For mode, timbre, note, force, and status bundles:

- hold the bundle stable around the request transaction;
- synchronize the transaction indicator, not each bit independently as an event;
- capture the whole bundle once in the destination;
- add an overrun flag if the source updates before acknowledgement.

## 6. Commit visual state only at frame boundaries

The LCD raster must not observe half-updated control state.

Recommended video-domain sequence:

1. receive a pending state bundle through a CDC transaction;
2. keep it in shadow registers;
3. on frame_start, copy shadow registers to active display registers;
4. render the entire frame from active registers.

Use this for mode labels, selected timbre, pressed-key colors, waveform parameters, and page changes. A stable background should be generated entirely from pixel coordinates and active frame state.

## 7. Double buffering and bank ownership

For waveforms, thumbnails, or rendered frames, distinguish writer ownership from reader ownership.

Minimum safe snapshot scheme:

- audio domain writes samples to the inactive waveform bank;
- after a complete block, it publishes the completed bank with a toggle;
- video domain accepts the new bank only at frame_start;
- video reads one immutable bank for the entire frame;
- writer never overwrites the bank currently displayed.

For external memory or variable-latency pipelines, use explicit bank states such as FREE, WRITING, READY, and DISPLAYING. Never infer ownership only from an address bit.

## 8. Parameter updates, limits, and lookup tables

A menu controller should own user-facing ranges and step sizes. Processing blocks should receive already validated parameters.

Good practices:

- saturate at documented minimum/maximum values;
- keep requested and committed values distinct when a CDC or fade is pending;
- use functions or case tables for small constants when synthesis support for initialized ROMs is uncertain;
- use named localparams for modes and error codes;
- expose invalid state or range violations as sticky diagnostics instead of silently wrapping.

## 9. Click-free audio transitions

Any discontinuous change can click: enable, mute, source, waveform, frequency word, gain, effect mode, or voice stealing.

Use one of these policies:

- gain ramp to/from zero for on/off;
- short crossfade for source or timbre changes;
- phase-continuous frequency changes for pitch bend;
- release-first or quietest-voice replacement for voice stealing.

Parameter transfer and fade execution belong in different layers: the control plane requests a change; the audio domain commits it at a sample boundary and reports completion.

## 10. Self-test must use the production path

A test tone or fixed multi-voice pattern should enter through the same PCM contract, mixer width, effects, output adapter, and serializer as normal synthesis.

Useful self-tests:

- left/right DC-safe tone and channel identification;
- three fixed notes for chord and saturation checks;
- 32 deterministic frequencies for polyphony/resource checks;
- impulse for latency and delay-line checks;
- waveform snapshot pattern for LCD bank-switch validation.

A bypass that avoids the normal chain proves only the bypass.

## 11. Reset and startup policy

Use asynchronous assertion and synchronous release independently in each clock domain. Define startup ownership explicitly:

- control mode has a legal default;
- LCD active state is initialized before visible output;
- audio output begins muted and ramps up only after clocks and serializers are ready;
- CDC toggles and acknowledgements begin in matching states;
- bank metadata begins with exactly one legal reader bank and one legal writer bank;
- sticky errors clear only by reset or an explicit diagnostic clear command.

Do not use a functional key as the only permanent reset path after the product UI needs all keys.

## 12. Staged implementation pattern

For mixed audio/video designs, use this order:

1. preserve the known-good clock, reset, LCD timing, and serializer baseline;
2. add observability and contract monitors;
3. introduce a normalized input event layer;
4. add a frame-committed LCD status block;
5. insert the unified PCM contract and test source;
6. replace the prototype oscillator with one parameterized voice;
7. validate envelope, pitch, and timbre changes on one voice;
8. add allocation and a balanced polyphonic mix tree;
9. add ADC-derived force/pluck/pitch controls through a virtual input model first;
10. add effects and waveform/FFT displays only after audio contracts are stable.

Every stage must have:

- a repeatable simulation or bench action;
- a visible or audible expected result;
- at least one failure indicator;
- a clean rollback point;
- build, timing, resource, and pin evidence before being called complete.

## 13. Review checklist for Gowin projects

Before accepting a cross-vendor-inspired change, verify:

- [ ] all clocks and resets come from the current Gowin project;
- [ ] every CDC path has an explicit mechanism and destination-domain reset;
- [ ] stalled streams keep payload stable;
- [ ] unselected sources cannot consume data;
- [ ] LCD state changes only at a frame boundary;
- [ ] waveform/frame banks have explicit ownership;
- [ ] gain and mix widths include headroom and final saturation;
- [ ] mode/timbre/source changes cannot create a full-scale discontinuity;
- [ ] test sources travel through the production chain;
- [ ] sticky errors and counters are observable;
- [ ] vendor primitives and constraints were re-derived from Gowin documentation;
- [ ] simulation, synthesis, timing, resource, pin, and board evidence were collected.
