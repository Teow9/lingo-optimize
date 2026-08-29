---
name: lingo-optimize
description: >-
  用 LINGO 18 求解优化问题并把结果导出为 CSV 供 Python 绘图分析。涵盖：线性规划 LP、
  整数规划 MIP/IP、非线性规划 NLP、目标规划、运输/指派/排班/选址/网络流/配比/库存/投资组合/
  背包/TSP 等数学建模典型题型，以及灵敏度分析、最优解求解、"@POINTER 数据桥接"。
  当用户提到 LINGO、求解最优解、优化模型、lingo_runs、用 Python 调求解器、
  solve an optimization problem、optimal solution、operations research ——
  即使没点名 LINGO，只要任务是"求最优解/最小化/最大化某个目标"且环境里有
  LINGO64_18，就使用本 Skill。本 Skill 让 AI 一次写出语法正确的 LINGO 模型
  （大模型最常见的失败是 LINGO 语法错乱、反复返工），并产出可直接用
  pandas/matplotlib 分析的 CSV 结果（summary/variables/constraints/trace/sensitivity）。
---

# lingo-optimize：Python 规范化调用 LINGO 求解优化问题

**原理**：`scripts/lingo_runner.py` 用 ctypes 调用 `%LINGO64_18_HOME%\Lingd64_18.dll`
（进程内、零编译、已实测），把模型交给 LINGO 求解引擎，解析求解报告并输出
CSV 五件套。你要做的是：**写对模型 → 调 runner → 读结果**。

## 0. 硬性规则（每条都是实测踩过的坑，违反必翻车）

1. **写模型前先读** `references/lingo_syntax.md`（尤其"高频错误自查清单"）。
   你对 LINGO 语法的先验记忆大概率是错的——以该文件为准。
2. **只写纯文本 `.lng` 模型**（`MODEL:` 开头、`END` 结尾）。绝不产出
   `.lg4`（二进制 GUI 格式）、绝不混入旧式 LINDO 语法（`SUBJECT TO`、`Row)`）。
3. **脚本中 `TAKE` 的路径**：绝对路径 + 正斜杠 + **不加引号**（引号会作为
   文件名的一部分导致 Error 7；含空格不加引号反而没问题）。
4. **`@POINTER(n)` 槽位必须从 1 连续编号**且与注册顺序一致；数值输出槽要
   预先声明长度，长度错了 LINGO 会静默少写（见 `references/data_bridge.md`）。
5. **输出指针初始化为哨兵值**并由 runner 校验——区分"模型没跑"与"跑出 0 解"。
6. **不要在模型里用未知脚本命令**（如 `SET RANGS`——不存在的参数会让 LINGO
   进入 `Parameter?` 交互提示并永久挂起）。runner 已内置 300s 硬超时兜底。
7. **一次求解一个 LINGO 环境**（runner 已封装：每次运行独立 env）。
8. 中文只能出现在注释里；集合成员名/变量名只用 ASCII。

## 1. 标准工作流

### 第 1 步：读语法参考，按题型找模板

- 语法规则与 11 条高频错误：`references/lingo_syntax.md`（**必读**）。
- 三个可直接改写的模板（均已实测求出正确最优解）：
  - `assets/templates/transport_sets.lng` —— SETS/DATA 运输问题（LP 范式）
  - `assets/templates/integer_program.lng` —— 0-1 混合整数（@BIN 指示变量）
  - `assets/templates/pointer_bridge.lng` —— @POINTER 数据桥接（数组进出）
- 想找官方同题型样例对照：`references/model_library.md`（按题型索引本机
  120+ 教材模型与功能演示）。
- 需要 @ 函数确切签名：`references/functions.md`（127 个精选函数带官方描述）。

### 第 2 步：写模型 `.lng`

- 把用户的优化问题翻译成 LINGO 模型：目标（`MIN =`/`MAX =`）+ 约束 +
  变量域（`@GIN/@BIN/@FREE/@BND`）+ 行标签 `[Name]`。
- 数据通道三选一（详见 `references/data_bridge.md`）：
  - **内插 DATA 段**（默认）：Python 生成模型时把数据写死在 `DATA:` 里；
  - **`@POINTER` 桥接**：数组数据/要精确回传解时用；
  - **`@TEXT`/`@FILE`**：数据放独立文本文件，模型参数化重跑。
- 模型保存到用户项目目录（建议 `lingo_runs/` 下），扩展名 `.lng`。

### 第 3 步：求解

```bash
python "<skill目录>/scripts/lingo_runner.py" model.lng \
       [--out 输出目录] [--inputs ptr.json] [--vars X,Y] \
       [--no-trace] [--no-sensitivity] [--timeout 300]
```

- 默认输出目录：`./lingo_runs/run_<时间戳>/`（相对当前工作目录）。
- runner 在子进程中求解（300s 硬超时，超时杀进程报错，不会挂死会话）。
- **stdout 输出一个 JSON**：`status_text`、`objective`、`gap`、`iterations`、
  `pointer_outputs`、`warnings`、`files`（各 CSV 路径）。先读这个 JSON。
- 退出码：0=求得最优（全局/局部）；1=不可行/无界/未定；2=调用或系统错误。

### 第 4 步：汇报结果

向用户报告：**求解状态**（全局最优/局部最优/不可行/无界）、**目标值**、
关键变量的取值（读 `variables.csv` 或 JSON 的 `variables`）、约束使用情况
（`constraints.csv` 的 slack=0 说明该约束是紧的）、迭代与耗时。
若有 `warnings`（如 Error 121 表示整数模型无灵敏度），如实转述。

### 第 5 步：绘图分析（Python 读 CSV）

```python
import pandas as pd, matplotlib.pyplot as plt
run = "lingo_runs/run_20260829_160000"
v = pd.read_csv(f"{run}/variables.csv")
t = pd.read_csv(f"{run}/trace.csv")
# 收敛曲线（MIP 下界逼近过程 / LP 单点）
plt.plot(t["t_sec"], t["best_bound"] if t["best_bound"].notna().any() else t["incumbent"])
plt.xlabel("time (s)"); plt.ylabel("objective"); plt.show()
```

## 2. CSV 产出速查（utf-8-sig，可直接 `pd.read_csv`）

| 文件 | 关键列 | 用途 |
|---|---|---|
| `summary.csv` | status_text, objective, mip_bound, gap, iterations, model_class, n_variables, n_integer_vars, elapsed_sec | 单行总览，论文/报告引用 |
| `variables.csv` | name, value, reduced_cost | 全部对象取值（含集合属性成员，如 `VOLUME( WH1, C1)`）；reduced_cost>0 的非基变量提示 |
| `constraints.csv` | row_name, slack_or_surplus, dual_price | 松紧分析（slack=0 紧约束）与影子价格 |
| `trace.csv` | t_sec, iterations, objective, mip_bound, incumbent, best_bound, gap | 收敛过程画图；MIP 的 best_bound 单调逼近，objective 是节点松弛值（有噪声） |
| `sensitivity.csv` | section(objective_coefficient/rhs), name, current_value, allowable_increase, allowable_decrease | LP 灵敏度（RANGES 报告）；INFINITY 输出为 inf；整数/非线性模型自动跳过 |
| `lingo_run.log` | — | 原始求解报告与模型回显，排错用 |

## 3. `@POINTER` 桥接速记（细节见 data_bridge.md）

- 模型：输入 `NEEDS = @POINTER(1);`，输出 `@POINTER(3) = START;`
  `@POINTER(4) = @STATUS();`——槽号从 1 连续。
- Python（`ptr.json`）：
  ```json
  {"inputs":  {"1": "MON TUE WED", "2": [17, 13, 15]},
   "outputs": {"3": 7, "4": 1}}
  ```
  字符串输入是集合成员名（空格或换行分隔均可）；数值输出槽写长度；
  字符串输出槽写 `"str"`（回传"被选中成员"名单，knapsack 模式）。
- 结果在 JSON `pointer_outputs` 里按槽号取用。

## 4. 排错速查

| 现象 | 原因与处理 |
|---|---|
| Error 7 无法打开文件 | TAKE 路径加了引号 → 去掉引号 |
| Error 11 语法错误 | 按语法文档自查；注意 `!` 注释内出现 `;` 会提前终止注释 |
| Error 37 名字已占用 | 行标签 `[CAP]` 与属性重名 → 换标签名 |
| Error 121 | 整数/非线性模型不支持灵敏度（正常现象，非故障） |
| `Parameter?` 挂起后超时 | 模型/脚本里有未知命令，LINGO 在等交互输入 |
| 指针输出为 None | 输出槽长度没给够或槽号与模型 `@POINTER` 编号错位 |
| 状态 6（局部最优） | MIP 求解正常完成；非凸非线性模型若要全局最优，加 `--global` 重新求解（runner 会 `SET GLOBAL 1` 启用全局求解器，手册 §72） |
| 变量表出现 `CAPACITY( WH1)` 这类行 | 正常：LINGO 把 DATA 属性也列进报告，`variables.csv` 一并保留 |

## 5. 环境前提（本机已满足）

- `LINGO64_18_HOME` 环境变量指向 LINGO 18 安装目录（`E:\Tools\LINGO64_18`），
  且该目录在 PATH 中；许可为 Site 全功能（线性/整数/非线性/全局/随机/锥）。
- Python ≥3.8，仅标准库（不需要 numpy）。
- runner 与 LINGO DLL 的绑定签名依据 `Programming Samples\Lingd18.h`，
  修改 LINGO 版本后如遇加载失败，核对该头文件的 9 个 `LS*Lng` 函数签名。
