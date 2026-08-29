# 本机 LINGO 样例模型库索引（按题型）

> 用途：写模型前，找一个**最接近用户问题**的官方样例参照其建模结构。
> 所有路径相对 `E:\Tools\LINGO64_18\`。

## ⚠️ 文件格式须知

- `.lng` / `.ltf` / `.ldt` / `.txt`：**纯文本**，可直接读。
- `.lg4`：**OLE2 二进制容器**（274/283 个），模型文本嵌在内部的 "Contents"
  流中，可用 `strings 文件 | head -80` 提取（内嵌两份，取第一份）。
  少数 .lg4 是纯文本（如 `Samples\WIDGETS.lg4`、`Samples\TSP.lg4`）。
- 不要把 .lg4 当文本复制改写后求解——Skill 产出的模型一律是纯文本 `.lng`。
- 完整目录说明：`Samples\SampText\INDEX.TXT`（教材《Optimization Modeling
  with LINGO》120 个模型的逐条题解说明，纯文本，值得先读）。

## SampText\ —— 教材模型（CH章节M编号.lg4，INDEX.TXT 有逐条说明）

| 章节 | 主题 |
|---|---|
| CH01–CH03 | 产品组合入门、整数规划入门、成本计算 |
| CH04 | 建模方法论（构造法、沉没成本/联合成本、常见错误） |
| CH05 | 集合语法专题：原始集 CH05M01（排班）、稠密派生集 CH05M02、稀疏集显式列举 CH05M03、成员过滤 CH05M04 |
| CH06–CH07 | 产品组合、人员排班 CH07M01、下料 CH07M02、班组调度 CH07M03 |
| CH08 | **网络流专题**：三级配送 CH08M01、PERT/CPM CH08M02–04、路径 formulation CH08M05–06、多商品流 CH08M07、机队路由 CH08M08–10、最小生成树 CH08M12、Steiner 树 CH08M13、非线性网络 CH08M14 |
| CH09 | 多周期规划、现金流匹配 CH09M02、税务 CH09M04–05 |
| CH10 | **配比/混料专题**：Pittsburgh 钢厂配比 CH10M01、产品质量解释 CH10M04、池化问题 CH10M05 |
| CH11 | **整数规划专题**：分支定界 CH11M01、指派 CH11M03、**TSP CH11M04**、线性排序 CH11M05、装填 CH11M06、捆绑销售 CH11M07 |
| CH12 | 不确定性决策：二叉树、动态规划、期权定价 |
| CH13 | **投资组合专题**：Markowitz 均值方差 CH13M01–02、无风险资产 CH13M03、交易成本 CH13M06、情景模型 CH13M10、半方差 CH13M12 |
| CH14 | 多目标：目标规划 CH14M03、DEA 数据包络 CH14M08、Pareto 有效点 |
| CH15 | 经济均衡：供需曲线、拍卖、一般均衡 |
| CH16 | 博弈：Minimax CH16M01–02、双矩阵 CH16M03 |
| CH17 | **随机库存专题**：报童模型（正态需求）CH17M01、多级报童 CH17M02、(Q,r) 库存 CH17M06、多产品能力约束批量 CH17M11–12 |
| CH18 | 列生成（下料问题）CH18M01 |

## Samples\ 根目录（官方功能演示，多为 .lg4）

| 文件 | 主题/亮点 |
|---|---|
| `WIDGETS.lg4`、`TRAN.ltf`（根目录） | 运输问题（纯文本，SETS/DATA 标准范式） |
| `STAFFPTR.lng`、`STAFFPTR2.lng`、`QUEUEPTR.lng`、`SIMPLE.lng` | **@POINTER 桥接官方范例**（纯文本，Python 接口配套） |
| `KALMANFILTER.lg4` | 卡尔曼滤波 + @POINTER |
| `DOGS.ltf` | 命令脚本范例（SET/GO/@FILE/@TEXT 文件 I/O） |
| `TRANTEXT.lg4`、`TRANWH.ldt`、`TRANROUTES.ldt` | @TEXT 文件读数 + 运输问题 |
| `TRANOLE.lg4`/`TRANOLE.xls`、`STAFFOLE.xls` | @OLE 与 Excel 交互 |
| `TRANDB.lg4`/`TRANDB.mdb`/`TRANDB.sql` | @ODBC 数据库读取 |
| `BLEND.lg4`、`CHESS.lg4` | 配比、国际象棋棋盘 |
| `TSP.lg4`（纯文本）、`AROUTE3.lg4`、`VROUTE.lg4` | 车辆路径/TSP |
| `CRASHCPM.lg4`、`CHARTGANTT.lg4` | 项目管理 CPM/甘特图 |
| `DEAMOD.lg4`、`CHOLESKY.lg4`、`EIGENEX1.lg4` | DEA、矩阵分解/特征值 |
| `BAYES.lg4`（纯文本）、`DNRISK.lg4`、`DYNAMB.lg4` | 贝叶斯、决策风险、动态规划 |
| `EOQCAP.lg4`、`COSTING.lg4`、`BOX.lg4` | 经济订货批量、成本核算、装箱 |
| `CONVEX.lg4`、`CHMBL1.lg4` | 凸规划、化学平衡（非线性） |

## Hillier\ ——《运筹学导论》教材配套（chap03–chap22、26、27）

- `.lg4` 内是 LINGO 语法（提取方法见上）；**`.ltx` 是旧式 LINDO 语法，只看思路勿抄语法**。
- 代表性模型：`chap03\ling03_Wyndor.lg4`（LP 入门）、`chap08\ling08_Metro_water.lg4`
  （运输+SETS 完整范式）、`chap11\Ling11_Good_Products.lg4`（@BIN 指示变量 IP）、
  `chap09\ling09_Shortest_path.lg4`（最短路）、`chap27\Ling27_Regression.lg4`（回归）。
- 章节→主题：chap03 线性规划入门、chap06 对偶、chap07 敏感性、chap08 运输与指派、
  chap09 网络模型、chap11 整数规划、chap12–13 非线性、chap17 排队论、
  chap18 存储论、chap19 马尔可夫、chap20 仿真、chap22 PERT。
- `Hillier\Intro_to_LINGO.doc` 是 LINGO 建模入门教程（Word 二进制）。

## 使用建议

1. 先按题型在上表定位 1–2 个样例，提取其模型文本（`.lng` 直接读，`.lg4` 用 strings）。
2. 对照 `lingo_syntax.md` 套用其结构（SETS 布局、@FOR 模式、域声明位置）。
3. 数据替换为用户数据（通道选择见 `data_bridge.md`），用 `lingo_runner.py` 求解。
