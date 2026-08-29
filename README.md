# lingo-optimize

**把 LINGO 18 变成 Python 可调用的高精度优化求解器 —— 一个面向"约束优化问题求解"这一类任务的通用技能。**

本技能不绑定任何特定的 AI 编程助手。它遵循开放的 Agent Skills 规范（`SKILL.md`
入口 + 渐进式披露的参考文档 + 自包含脚本），任何支持该规范的 AI Agent（如
Claude Code、ZCode、OpenCode 等）都可以加载使用；同时它本身也是一个零第三方
依赖的 Python 命令行工具和库 —— 没有 Agent、甚至完全不经过 LLM，也能直接使用。

## 适用的问题类

凡是"在约束条件下求目标函数最优（最小化/最大化）"的数学规划问题都在覆盖范围内：

- **模型类型**：线性规划 LP、混合整数规划 MIP/IP、0-1 整数规划、非线性规划
  NLP（可启用 LINGO 全局求解器处理非凸问题）、目标规划等；
- **典型题型**（运筹学 / 数学建模竞赛）：运输、指派、排班与调度、选址、网络流/
  最短路/最小生成树、配比混料、库存、投资组合、背包、TSP/VRP、下料、博弈与
  经济均衡、随机规划等；
- **配套分析**：LP 灵敏度（ranging）分析、对偶价格/影子价格、MIP 上下界与
  gap、求解收敛过程追踪，结果可直接用 pandas/matplotlib 出图。

只要任务是"求最优解"且环境里有 LINGO 18，就适用本技能 —— 无论是否点名 LINGO。

## 核心价值：让模型一次写对

LLM 写 LINGO 模型的最大痛点是语法错乱、反复返工 —— LINGO 与旧式 LINDO 是两套
语言（`MIN =` 必须有等号、分号规则、SETS/DATA 集合语法……），模型记忆稍旧就
会产出无法求解的代码。本技能把"防幻觉"知识直接内置进技能包：

- `references/lingo_syntax.md` —— 从官方样例与 985 页用户手册提炼的语法规范 +
  11 条高频错误自查清单（写模型前必读）；
- `assets/templates/` —— 3 个已实测求出正确最优解、可直接改写的模板；
- `references/model_library.md` —— 本机 120+ 官方样例模型按题型索引；
- `scripts/lingo_runner.py` —— 零编译 ctypes 调用，子进程硬超时防挂死。

这些知识属于技能包本身，与宿主 Agent 无关 —— 换任何 Agent、开任何新会话，
技能表现一致。

## 求解产出

每次求解输出一个结果目录（utf-8-sig 编码，可直接 `pd.read_csv`）：

| 文件 | 内容 |
|---|---|
| `summary.csv` | 求解状态、目标值、MIP 下界/gap、迭代次数、模型类别、耗时等单行总览 |
| `variables.csv` | 每个变量/属性成员的取值 + reduced cost |
| `constraints.csv` | 行标签、slack/surplus、对偶价格 |
| `trace.csv` | 求解器回调追踪（目标值、MIP 下界、当前最优解），用于画收敛曲线 |
| `sensitivity.csv` | LP 灵敏度报告（目标系数 + 右端项 ranging），MIP/NLP 自动跳过 |
| `lingo_run.log` | 原始 LINGO 日志（模型回显 + 完整求解报告），排错用 |

## 环境要求

- Windows + LINGO 18 已安装，环境变量 `LINGO64_18_HOME` 指向安装目录
  （任何能加载 `Lingd64_18.dll` 的许可均可运行；灵敏度分析、全局求解等完整
  功能需要相应许可项支持）
- Python ≥ 3.8，仅标准库（不需要 numpy）

## 安装与使用

### 方式一：作为 AI Agent 的技能（推荐）

技能包对宿主的要求只有两点：能读取 `SKILL.md` 的 YAML frontmatter
（`name`/`description` 用于触发匹配），并允许执行 `scripts/` 下的 Python 脚本。
把整个目录复制进所用 Agent 的技能目录即可：

```bash
# 通用跨 Agent 技能目录（多个主流 Agent 共享识别）
cp -r lingo-optimize ~/.agents/skills/

# 或各 Agent 自己的技能目录（以对应文档为准），例如：
#   ~/.claude/skills/ 、~/.zcode/skills/ 、<项目>/.agents/skills/ 等
```

装好后用自然语言提需求即可，例如"用 LINGO 求解这个运输问题并画出收敛曲线" /
"solve this LP with LINGO and export CSVs"。技能的触发条件、工作流、硬性规则
见 `SKILL.md`。

### 方式二：直接命令行（无 Agent）

```bash
python lingo-optimize/scripts/lingo_runner.py model.lng \
    [--out DIR] [--inputs ptr.json] [--vars X,Y] \
    [--no-trace] [--no-sensitivity] [--global] [--timeout 300]
```

- 默认输出目录 `./lingo_runs/run_<时间戳>/`（相对当前工作目录）；
- stdout 输出一个 JSON：求解状态、目标值、gap、迭代次数、`@POINTER` 回传值、
  warnings、各 CSV 路径；
- 退出码：0 = 求得最优（全局/局部）；1 = 不可行/无界/未定；2 = 调用或系统错误；
- 求解在带 300s 硬超时的子进程中运行，模型有问题时杀进程报错，不会挂死终端。

### 方式三：作为 Python 库

```python
from lingo_runner import solve
result = solve("model.lng", out_dir="run1")   # 返回 dict，字段同 stdout JSON
```

## 目录结构

```
SKILL.md                  # 技能入口：触发条件 + 标准工作流 + 8 条硬规则 + 排错速查
scripts/lingo_runner.py   # ctypes -> Lingd64_18.dll，CSV 导出，子进程超时兜底
references/
  lingo_syntax.md         # 语法规范 + 11 条高频错误（防幻觉核心，写模型前必读）
  functions.md            # 127 个内置 @ 函数及官方描述
  data_bridge.md          # Python <-> LINGO 数据通道：内插 DATA / @POINTER / @TEXT-@FILE
  model_library.md        # 本机 120+ 官方样例模型按题型索引
assets/templates/         # 实测模板：运输 LP、0-1 MIP、@POINTER 数据桥接
```

## 工作原理

`lingo_runner.py` 通过 ctypes 加载 `%LINGO64_18_HOME%\Lingd64_18.dll`（进程内、
零编译，无需构建 pyLingo），按槽位注册 `@POINTER(n)` 输入/输出缓冲区，在
**超时保护的子进程**里执行一条 LINGO 命令脚本（`SET ECHOIN/TERSEO/DUALCO` →
`TAKE model.lng` → `GO` → `RANGES` → `QUIT`），解析求解报告后写出上面的 CSV
结果包。`SKILL.md` 记录了实测踩过的坑（`TAKE` 路径不加引号、指针槽位必须从 1
连续编号、未知 SET 参数触发 `Parameter?` 交互挂起等）。每次求解新建并销毁
独立的 LINGO 环境，可安全地反复调用。

## 可移植性设计（为什么它是通用技能）

- **标准入口**：`SKILL.md` 使用 Agent Skills 通用的 YAML frontmatter + Markdown
  正文格式，不含任何特定宿主的私有指令语法；
- **渐进式披露**：入口正文保持精简，细节按需引用 `references/`，上下文开销
  可控，对长会话和上下文受限的宿主友好；
- **自包含脚本**：runner 仅依赖 Python 标准库 + LINGO 自带 DLL，不依赖宿主
  Agent 提供的任何额外工具或运行时；
- **无状态产物**：所有输出落在运行目录（CSV + log），由调用方（Agent 或人）
  自行读取，技能本身不依赖任何会话历史。

## 已知限制与版本适配

- 灵敏度分析仅适用于纯 LP；MIP/NLP 模型会优雅跳过（LINGO error 121 属预期，
  非故障）。
- 非凸 NLP 默认可能只得到局部最优，加 `--global`（`SET GLOBAL 1`）启用
  LINGO 全局求解器。
- 仅支持 Windows（依赖 `ctypes.WinDLL` 与 LINGO Windows 版 DLL）。
- 已在 LINGO 18.0.44 上测试（DLL API `Lingd64_18`，LINDO API 12.0）；更换
  LINGO 版本后如 DLL 加载失败，核对 `Programming Samples\Lingd18.h` 中 9 个
  `LS*Lng` 导出函数签名（runner 的绑定即依据该头文件）。
