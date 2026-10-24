# Cross-Vendor FPGA Reference Porting

Use outside-vendor code to answer questions such as debounce structure, clock
domain crossing, frame buffering, or pixel pipeline organization. It is not
evidence for Gowin package pins, bank voltage, timing syntax, device resources,
or programming commands.

## Required re-checks

1. Read the current `.gprj` device and part number, then confirm the board
   revision and primary oscillator from current board evidence.
2. Map each external interface again: package pin, bank voltage, I/O standard,
   pull mode, drive, polarity, and reserved configuration/JTAG resources.
3. Replace vendor-specific primitives and generated IP. For PLLs, SERDES,
   DDR/IOLOGIC, RAM, and hard blocks, regenerate the Gowin implementation and
   inspect its synthesis mapping.
4. Translate constraints into the active Gowin CST/SDC files. Do not paste
   another vendor's pin names, timing commands, generated-clock objects, or
   false paths without checking the post-synthesis object names.
5. Use the Gowin Programmer flow for the scanned target. Never reuse an
   outside-vendor cable index, device ID, image format, Flash operation, or
   persistent/volatile mode.

## Acceptance

Keep the reference provenance in the work log. The migrated result is accepted
only after fresh RTL/synthesis/P&R/timing/pin/bitstream evidence for the Gowin
target. A passing source-vendor build or a copied bitstream does not count.
