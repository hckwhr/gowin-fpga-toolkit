# Select Project and Vendor References

Find documentation in the user's installed Gowin EDA or the official vendor
distribution. This skill does not bundle licensed manuals, course archives,
board schematics or generated vendor IP. Do not assume a fixed installation
path or that an example board is the current target.

| Question | Relevant document family |
|---|---|
| IDE project flow | SUG100, Gowin Software User Guide |
| Tcl and gw_sh | SUG1220, Gowin Software Tcl Command User Guide |
| Synthesis behavior | SUG550, GowinSynthesis User Guide |
| CST physical constraints | SUG935, Gowin Design Physical Constraints User Guide |
| SDC timing constraints | SUG940, Gowin Design Timing Constraints User Guide |
| RTL resource inference | SUG949, Gowin HDL Coding Style User Guide |
| Optimization and analysis | SUG113, Gowin Device Design Optimization and Analysis User Guide |
| Programmer | SUG502 and the exact device's programming/configuration guide |
| Pins, bank supplies and clocks | Exact board revision schematics, device/package pinout and official CST |

Manual versions must match the active EDA/device. The original workflow used
EDA V1.9.12.03, including SUG1220-2.0, SUG940-2.0.4, SUG949-2.2 and SUG113-1.3;
these are reference versions, not universal compatibility promises.

For Tang boards, obtain matching SOM/Dock schematics from Sipeed. Record
document revision and pin-table evidence in the project. A filename in a board
profile is provenance to inspect, not proof that the server has fetched or
electrically validated that document.

Installed examples under `IDE/data/examples` can explain tool syntax and IP
integration. Historical reports prove only their original builds; example
CST files never replace the active board pin audit.
