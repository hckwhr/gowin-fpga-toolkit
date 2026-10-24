# Sources and third-party boundaries

The MCP implementation, tests and skill text distributed here are original
code and independently written engineering guidance. This repository does
not bundle vendor manuals, course archives, licensed EDA executables, generated
vendor IP, or third-party project runtimes. Referenced material retains its
own copyright and license; this repository's MIT license does not relicense it.

## Vendor documentation

- Gowin SUG100, SUG113, SUG550, SUG935, SUG940, SUG949, SUG1220 and SUG502:
  consult the documents supplied with the matching EDA/device version.
  [Gowin official site](https://www.gowinsemi.com/).
- Sipeed Tang Mega 138K SOM 30354 / Dock 31005 schematics and official CST:
  used to prepare the optional board profile. Documents are not redistributed.
  Obtain revision-specific originals from [Sipeed](https://wiki.sipeed.com/).

Pin names and example wiring are revision-specific factual data. The profile
is not an endorsement by Gowin or Sipeed, nor a substitute for schematic review.

## Engineering references

The skill references cite pinned revisions where available. They adapt ideas
such as explicit contracts, report-driven experiments and evidence levels;
they do not install the source projects or copy their command runtimes.

| Reference | Reviewed revision | Upstream license |
|---|---|---|
| [lowRISC style guides](https://github.com/lowRISC/style-guides) | `9c15ff5dce23eef969e00ab3715153967419eadd` | Apache-2.0 |
| [CHIPS Alliance Verible](https://github.com/chipsalliance/verible) | `c1d8f5e8be4105726ce09b01de14ff0716f303bf` | Apache-2.0 |
| [AMD/Xilinx Ross](https://github.com/Xilinx/ross-ai-assistant) | `2cdc9eef1b6b5b17fa45f5e4d468e5483a1c92de` | MIT |
| [Eriemon Verilog Generator](https://github.com/Eriemon/verilog-generator) | `007372fb63fe1d0b51e5bb10f4569d0b62ae6730` | Apache-2.0 |
| [Eriemon HLS Generator](https://github.com/Eriemon/hls-generator) | `8a22caae4bdc1b5bb6191ef1ed82b63e92d1280a` | Apache-2.0 |

Eriemon projects identify Jiyuan Liu, He Li and Southeast University HIQC as
authors and are separate from AMD's projects. Mixed audio/video and debugging
notes also incorporate independently rewritten vendor-neutral lessons from
Anlogic course examples. The original examples and personal solutions are not
included or offered under this repository's license.
