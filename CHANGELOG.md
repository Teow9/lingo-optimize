# Changelog

记录 lingo-optimize 技能包的版本变更。版本号取 `主.次` 两位（技能包规模小，暂不启用补丁位）；
所有变更均以真实项目实测为依据，不做无证据的规则堆砌。

## [v1.1] - 2026-08-29

依据：2023 CUMCM B 题项目 9 次 LINGO 实跑踩坑的逐字复核（源码 + 四份运行日志）。

### Changed

- **状态判定重写**（`scripts/lingo_runner.py`）：`status_text` 只锚定日志报告段——
  `No feasible solution found.` / 非零 `Infeasibilities` → INFEASIBLE；
  `Global/Local optimal solution found.` → 最优；无报告段 → **NOT SOLVED**。
  不再对整份日志做关键词扫描：模型回显与中途警告（`may be nonoptimal/infeasible`）
  不再影响判定；`objective` 等统计量同样只从报告段解析；矛盾报告（声称最优但
  残留不可行量）发 warning 供人工核对。
  事实依据：LINGO 18 不可行报告并无 "INFEASIBLE" 字样（实测标记为
  `[Error Code: 81]` + "No feasible solution found." + 非零 `Infeasibilities`）。
- 高频错误自查清单 **11 → 14 条**（`references/lingo_syntax.md`）：新增
  ① 单行长度上限（约 800 字符，Error 3 "Overlength line"，数据被截断）；
  ② 内联 DATA 总量上限（约 1 MB，Error 62 "Ran out of workspace in model
  generation"，模型未进入求解）；③ 防御性 `@BND`（0-1/有界语义双界写全，
  不依赖"默认非负 + 条件门控"）。新增 §4.1 超长矩阵数据的分块书写模式（`fmt_data`）。
- `SKILL.md`：硬性规则 8 → 9 条（模型体量硬约束）、排错速查表 +2 行
  （Error 3 / Error 62）、"第 4 步"补状态口径说明；`README.md` 同步并新增版本小节。

### Added

- **求解前 advisory lint**（`lingo_runner.py`）：单行超长 / 内联 DATA 体量 /
  变量域缺失（声明了部分变量域但仍有属性缺域时点名提示，曾命中漏写 SB/SE 上界的
  真实事故）；结果进 stdout JSON `warnings`，不阻断求解。
- **离线回归自测** `scripts/self_test.py`：15 项断言，无需安装 LINGO 即可运行；
  `assets/fixtures/` 收录 5 份真实 LINGO 18 运行日志样例，含"无 Error 92 警告的
  不可行报告"回归样例（旧版会将其误判为 FEASIBLE）。
- SKILL.md / README.md 版本记录小节。

### 兼容性

- stdout JSON 字段、CSV 五件套（summary / variables / constraints / trace /
  sensitivity）、退出码映射**全部不变**；下游 Python 消费代码零改动。

## [v1.0] - 2026-08-29

### Added

- 首个版本：
  - `scripts/lingo_runner.py` —— ctypes 进程内调用 `Lingd64_18.dll`，输出
    CSV 五件套（utf-8-sig，可直接 `pd.read_csv`）+ stdout JSON；300s 子进程
    硬超时防挂死；`@POINTER` 槽位协议与哨兵校验；
  - `references/lingo_syntax.md` —— LINGO（≠ LINDO）语法规范 + 11 条高频错误
    自查清单；
  - `references/functions.md` / `data_bridge.md` / `model_library.md` ——
    内置 @ 函数速查、Python↔LINGO 数据通道协议、本机样例模型库索引；
  - `assets/templates/` —— 3 个实测可跑的模型模板（运输 LP、0-1 MIP、
    @POINTER 桥接）。

[v1.1]: https://github.com/Teow9/lingo-optimize/releases/tag/v1.1
[v1.0]: https://github.com/Teow9/lingo-optimize/releases/tag/v1.0
