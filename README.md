# Gowin FPGA Toolkit

面向 AI 辅助高云 FPGA 开发的 **MCP 服务 + Verilog/SystemVerilog Skill**。

A stdio MCP bridge and an agent skill for Gowin FPGA development: inspect
projects, run persistent builds, review timing and pins, and verify RTL contracts.

本仓库将工具与开发经验单独开源，适合在 Codex 或支持 stdio MCP 的客户端中使用。
MCP 负责调用工具和读取实际报告；Skill 提供 RTL、CDC、约束、验证与交付规范。
二者可以配合，也可以独立使用。项目非高云半导体官方产品。

## 包含什么

| 组件 | 路径 | 用途 |
|---|---|---|
| Gowin MCP 0.5.1 | [gowin-mcp/](gowin-mcp/) | Python 标准库实现，无第三方运行依赖 |
| Gowin / Verilog Skill | [skills/gowin-fpga/](skills/gowin-fpga/) | 可综合 RTL、资源推断、CDC、时序与验证指导 |
| 引脚配置 Schema | [board-profile.schema.json](gowin-mcp/board-profile.schema.json) | 板卡修订、器件、证据和引脚属性描述 |
| 示例板卡 Profile | [profiles/](gowin-mcp/profiles/) | Tang Mega 138K，SOM 30354 + Dock 31005，GW5AST-138C |
| 自动化测试 | [tests/](gowin-mcp/tests/) | 协议、构建归属、报告证据、时序和引脚边界 |

不包含比赛应用源码、ESP32 固件、上位机、厂商安装包、许可证、手册或历史位流。
示例板卡配置只覆盖部分低速资源，不是通用接线表，也不是任意 Tang 板卡的默认配置。

## 环境要求

- Python **3.10 或更高**，MCP 运行与单元测试均只用标准库。
- 支持 stdio MCP 的 AI 客户端。Skill 需要客户端支持目录式 `SKILL.md` 技能。
- 真正综合与布局布线需要自行安装并授权的 **Windows Gowin EDA**。
  原始桥接已在 **V1.9.12.03** 做过真实小工程构建验证；其他版本需要自行验证。
- 当前构建适配器查找 Windows 的 `IDE/bin/gw_sh.exe`；不宣称支持 Linux EDA 构建。

建议把工具和待构建工程放在 ASCII 路径。已验证版本的 `gw_sh` 对非 ASCII
工程路径存在兼容问题，服务会在构建前拒绝此类路径。

## 快速安装

```powershell
git clone https://github.com/hckwhr/gowin-fpga-toolkit.git C:/tools/gowin-fpga-toolkit
cd C:/tools/gowin-fpga-toolkit
python --version
python -m unittest discover -s gowin-mcp/tests -v
```

### 1. 配置 MCP

将以下内容合并到客户端的 MCP 配置中。所有路径均为示例，替换为自己的实际路径。
若 GUI 客户端找不到 `python`，将 `command` 改成 Python 可执行文件的绝对路径。

通用 JSON 配置示例：

```json
{
  "mcpServers": {
    "gowin": {
      "command": "python",
      "args": ["C:/tools/gowin-fpga-toolkit/gowin-mcp/server.py"],
      "env": {
        "GOWIN_HOME": "C:/Gowin/Gowin_V1.9.12.03_x64",
        "GOWIN_ALLOWED_ROOTS": "C:/fpga/workspace"
      }
    }
  }
}
```

Codex `config.toml` 等效示例：

```toml
[mcp_servers.gowin]
command = "python"
args = ["C:/tools/gowin-fpga-toolkit/gowin-mcp/server.py"]

[mcp_servers.gowin.env]
GOWIN_HOME = "C:/Gowin/Gowin_V1.9.12.03_x64"
GOWIN_ALLOWED_ROOTS = "C:/fpga/workspace"
```

两个环境变量必须显式配置为绝对路径：

| 变量 | 含义 |
|---|---|
| `GOWIN_HOME` | Gowin 安装根目录，其下应有 `IDE/bin/gw_sh.exe` |
| `GOWIN_ALLOWED_ROOTS` | 允许访问的工程目录，多个目录用英文分号 `;` 分隔 |

没有配置时服务拒绝相关操作，不会默认开放当前目录或用户目录。
如需使用仓库自带 Profile，将其目录另外加入允许范围，例如
`C:/fpga/workspace;C:/tools/gowin-fpga-toolkit/gowin-mcp/profiles`。

重启客户端后，先调用 `gowin_environment`，确认安装路径及 `gw_sh_exists`，
再调用 `gowin_inspect_project` 检查一个实际 `.gprj`。服务是 stdio 协议程序，
直接运行后等待输入是正常状态，不会弹出 GUI 或启动 HTTP 服务。

### 2. 安装 Skill

将 [skills/gowin-fpga](skills/gowin-fpga/) 整个目录复制到客户端的技能目录。
Codex 用户级目录通常为 `%USERPROFILE%/.codex/skills`；已有同名技能时先比较内容，
避免覆盖自己的定制版本。其他客户端使用各自的技能安装目录。

安装后可直接请求：

```text
使用 $gowin-fpga 检查这个工程的 Verilog、时钟和引脚约束，
先跑现有仿真，再综合；解释真实报告，不要直接烧录。
```

Skill 的入口是 [SKILL.md](skills/gowin-fpga/SKILL.md)，参考资料按需加载：

- [Verilog/SystemVerilog 编码规范](skills/gowin-fpga/references/verilog-coding-style.md)：赋值、位宽、符号、FSM、复位与 RAM/DSP 推断。
- [事务与验证契约](skills/gowin-fpga/references/contract-verification.md)：握手边沿、事件归属、同步 RAM、共享算力与负向测试。
- [开发流程](skills/gowin-fpga/references/development-workflow.md)：从工程与板卡确认到综合、布线和交付证据。
- [报告驱动优化](skills/gowin-fpga/references/report-driven-rtl.md)：实测资源、关键路径和有归因的实验。
- [Tcl/MCP](skills/gowin-fpga/references/tcl-and-mcp.md)：固定构建、任务状态与引脚计划。
- [跨厂商移植](skills/gowin-fpga/references/cross-vendor-porting.md)：复用算法与架构，重新核对器件、IP 和约束。

Skill 不是 Verilog 编译器；它指导 AI 使用现有工程与工具，不代替仿真、STA 或板上验证。

## MCP 工具

| 工具 | 行为 |
|---|---|
| `gowin_environment` | 只读检查工具路径与允许目录 |
| `gowin_inspect_project` | 解析 `.gprj`、器件、启用文件及缺失输入 |
| `gowin_start_build` | 启动独立构建进程，立即返回 `build_id` |
| `gowin_build_status` | 按 ID 读取持久状态、心跳、日志和产物 |
| `gowin_build_project` | 兼容等待接口；等待超时不会终止构建 |
| `gowin_diagnose_log` | 精确统计错误/警告及未布通数量，保留原始行号 |
| `gowin_read_report` | 有长度上限地读取工程内文本报告 |
| `gowin_timing_summary` | 解析时钟、Setup/Hold、TNS、Fmax、路径和覆盖情况 |
| `gowin_pin_audit` | 对照 CST 与最终引脚报告，检查冲突、漏约束和自动分配 |
| `gowin_plan_pins` | 根据指定板卡 Profile 生成引脚方案，不修改工程 |
| `gowin_apply_pin_plan` | 默认预览；显式应用时校验方案 ID、备份并原子替换 CST |

### 推荐构建流程

1. 检查工程、器件、输入文件、时钟与板卡证据，运行项目已有的 RTL 仿真。
2. 调用 `gowin_start_build`，先以 `stage="syn"` 检查综合结果。
3. 需要完整实现时使用 `stage="all"`，保存返回的 `build_id`。
4. 用相同 ID 调用 `gowin_build_status`；客户端重启后仍可继续查询。
5. 构建完成后分别运行 `gowin_timing_summary` 和 `gowin_pin_audit`。

全流程参数示例（作为 MCP 工具参数，不是终端命令）：

```json
{
  "project_file": "C:/fpga/workspace/example/example.gprj",
  "stage": "all",
  "budget_seconds": 7200,
  "place_option": 3,
  "route_option": 2
}
```

`place_option` 接受 0–4，`route_option` 接受 0–2；二者可省略，不能用于 `syn`。
示例中的 3/2 不是通用最优组合，应沿用当前工程有证据支持的设置。
服务会从厂商生成的 `impl/pnr/cmd.do` 检查实际生效值。

`budget_seconds` 是提醒阈值，不是强制杀进程时间。相同工程目录只允许一个
MCP 管理的构建；外部 GUI/CLI 构建不在锁的管理范围内，启动前须自行检查。
日志静默不能证明卡死，心跳正常也不能证明布线有进展。服务不会自动终止、
重跑或删除遗留锁；恢复前应先检查记录的进程与日志。

### 构建证据与产物

每轮记录保存在 `<工程目录>/.gowin-mcp/<build_id>/`，包括固定 Tcl、日志、
持久化 `receipt.json` 和 `reports/` 文本报告归档。
`.p`、`.pr`、`.fs` 等大二进制文件只记录原位哈希，不重复复制。

| 证据 | 含义 |
|---|---|
| `.p` | 放置产物，不能当作布线完成 |
| `.pr` | 布线产物 |
| `*_tr_content.html` | 完整时序报告；`.tr.html` 可能只是外层页面 |
| `.pin.html` | 最终引脚报告 |
| `.fs` | 位流，不证明已经烧录或实物功能正常 |

对于 `pnr/all`，`success=true` 要求正常退出、无日志错误、输入未变化、
请求选项一致，以及新鲜非空的布线、完整 STA、引脚和位流产物。
仅有 `0 unrouted nets`、退出码 0 或旧 `.fs` 都不够。

构建成功也不代表时序验收通过。缺失的时序计数或 slack 保持 `null`，
部分报告不能默认当作零违例；需检查实际 Setup/Hold 和时钟覆盖。
`timing_clean` 是解析器对报告与显式时钟覆盖的检查结果，并非形式化的全路径约束证明。
后续覆盖输出或修改输入会使旧状态失效，文本归档仍保留。

## 引脚计划

Profile 必须记录精确板卡修订、器件、封装料号、证据来源、可用引脚与电气属性。
先 `gowin_plan_pins` 审阅方案，再用相同输入及 `expected_plan_id` 调用
`gowin_apply_pin_plan`。默认 `apply=false` 只输出差异，明确 `apply=true` 才写入。
应用后还须重新构建并审计最终引脚报告。

服务检查 Profile 的一致性，不会自动下载原理图或核实证据文字是否真实。
仓库中的 Tang Mega 示例仅适用于其标注的修订，使用前应获取并核对列出的厂商资料。
DDR、HDMI、SerDes 等高速接口不在此示例覆盖范围。

## 测试与验证范围

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m unittest discover -s gowin-mcp/tests -v
```

当前含 **39 项**单元/协议测试：保留原 35 项，新增 4 项显式配置与拒绝越界测试。
覆盖异步任务、跨进程状态恢复、独占锁、超时不杀任务、报告归档、输入/输出失效、
缺失时序证据、零未布通假成功、引脚计划和 stdio 返回编码。
测试使用临时工程、模拟进程和合成报告，不要求安装 Gowin，也不证明硬件行为。

[live_smoke](gowin-mcp/tests/fixtures/live_smoke/) 是特定器件/引脚的小工程示例，
不会在单元测试中调用 EDA，也不能未经板卡核对就烧录。
本次公开打包未重新运行真实 EDA 构建或板卡测试。

## 使用边界与贡献

服务不提供下载器扫描、SRAM/Flash 烧录、擦除、OTP、密钥、安全配置，
也不提供任意 shell/Tcl 执行接口。构建仍会调用本机 EDA 并写入工程产物。
请只对可信工程开放目录；允许目录检查不是厂商进程沙箱，工程中的外部引用
及隐式 include 仍需自行审计。

反馈问题请附 Python/EDA 版本、器件、最小复现步骤和脱敏日志。
涉及报告解析时优先提供最小报告片段及预期字段，不要上传许可证或私有项目资料。
代码修改请运行全部测试；真实 EDA 或硬件验证请单独注明环境和范围。

## 许可与来源

本仓库原创代码及独立撰写文档使用 [MIT License](LICENSE)。
参考方法与厂商资料的归属见 [THIRD_PARTY.md](THIRD_PARTY.md)。
Gowin EDA、厂商 IP、手册和第三方项目遵循各自许可，不随本仓库重新授权。
