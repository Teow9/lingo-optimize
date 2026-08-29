# Python ↔ LINGO 数据桥接

> 回答一个问题：模型的数据从哪来、解往哪去。三种通道按模型复杂度选择，
> 通道细节均经本机实测验证。

## 0. 选型决策

| 场景 | 推荐通道 |
|---|---|
| 小型问题，数据就是几个常数 | **内插 DATA 段**：Python 直接把数值写进 `.lng` 文本 |
| 数据是数组/矩阵，或要把解**精确**读回 Python 做后续计算 | **`@POINTER` 桥接**（共享内存，无损、无需解析） |
| 数据量大 / 想让模型文件保持参数化、多次改数据重跑 | **`@TEXT`/`@FILE` 文件通道**（数据放独立文本文件） |
| 数据在 Excel / 数据库里 | `@OLE('workbook.xlsx')` / `@ODBC(...)`（Windows） |

## 1. 内插 DATA 段（默认首选）

Python 生成模型文本时用 f-string/模板把数据写死：

```lingo
DATA:
   CAPACITY = 30 25 21;
   DEMAND   = 15 17 22 12;
ENDDATA
```

注意：数值要在 Python 侧先格式化（`f"{x:.6g}"`），列表用空格连接；
集合成员名一律 ASCII 字符串。

## 2. `@POINTER` 桥接（runner 的指针协议）

### 2.1 模型侧写法（输入与输出都在 `DATA:` 段声明）

```lingo
DATA:
   NEEDS = @POINTER( 1);        ! 输入：读入一维数值数组（长度=集合大小）;
   DAYS  = @POINTER( 2);        ! 输入：读入集合成员名（一个空格分隔的字符串）;
ENDDATA
 [OBJ] MIN = @SUM( DAYS( I): START( I));
 @FOR( DAYS( I): @GIN( START( I)));
DATA:
   @POINTER( 3) = START;        ! 输出：把解写回指针（长度=集合大小）;
   @POINTER( 4) = @STATUS();    ! 输出：求解状态码（标量）;
ENDDATA
```

**规则（实测确认）**：
- `@POINTER(n)` 的 n 是**注册顺序号**：宿主第 n 次调用 `LSsetPointerLng`
  对应 `@POINTER(n)`。因此模型里的 n 必须是**从 1 开始的连续整数**。
- 等号方向即数据方向：`A = @POINTER(n)` 是**输入**（LINGO 从缓冲区读），
  `@POINTER(n) = A` 是**输出**（LINGO 把解写进缓冲区）。
- **集合成员名的官方协议**（手册 "Passing Set Members with @POINTER"）：
  所有成员名拼成**一个**字符串，用**换行符 `\n` 分隔**、NUL 结尾；
  空格会被 LINGO 剥离、不作为分隔符。runner 会自动把
  `"MON TUE WED"` 这类空格分隔输入转成换行协议。
- 数值输出缓冲区由宿主**预先按长度分配**；`@STATUS()` 输出占 1 个标量槽；
  字符串输出槽在 JSON 里写 `"str"`（见下）。

### 2.2 runner 侧协议（`--inputs pointers.json`）

```json
{"inputs":  {"1": "MON TUE WED THU FRI SAT SUN", "2": [8, 10, 9, 12, 11, 9, 6]},
 "outputs": {"3": 7, "4": 1, "5": "str"}}
```

- `inputs` 的值：**字符串** → 传为字符缓冲（集合成员名，空格自动转为
  官方换行分隔协议）；**数字或数字数组** → 传为 double 数组。
- `outputs` 的值：数值槽声明期望的**元素个数**（标量写 1，数组写长度）；
  字符串槽写 `"str"`（LINGO 会把成员名列表写回缓冲区，runner 返回名字数组）。
- 槽位号必须覆盖 `1..N` 连续（runner 会校验并拒绝跳号）。
- 求解后 runner 在 stdout JSON 的 `pointer_outputs` 里返回
  `{"3": [...], "4": 6.0, "5": ["ITEM1","ITEM2"]}`；若某数值槽位仍是哨兵值
  （未被模型写入）会给出 warning——通常是槽号与模型 `@POINTER` 编号没对齐。

### 2.3 结果状态码（`@STATUS()` 返回值）

| 码 | 含义 |
|---|---|
| 0 | 全局最优 |
| 6 | 局部最优（MIP 求解完成的常规返回） |
| 4 | 可行解（未证最优） |
| 1 | 不可行 |
| 2 | 无界 |
| 3 | 无法确定 |
| 9 | 数值错误 |

## 3. `@TEXT` / `@FILE` 文件通道

### 3.1 读数据：`@FILE('文件名')` 或 `@TEXT('文件名')`

数据文件是自由格式文本（空格/逗号分隔，`!` 注释，`~` 可作行分隔），
官方范例见 `Samples\TRANWH.ldt`、`Samples\Linux\PLUTO.ldt`：

```lingo
DATA:
   WAREHOUSE, CAPACITY = @TEXT('tranwh.ldt');
   CUSTOMER,  DEMAND   = @TEXT('trancust.ldt');
   ROUTES,    COST     = @TEXT('tranroutes.ldt');
ENDDATA
```

- 路径**相对于运行目录**；文件名含空格时同样**不要加引号转义**——最稳的
  做法是把数据文件与模型放在同一目录、只用文件名。
- Python 侧把数据写成这种文本文件即可，模型无需改动就能换数据重跑。

### 3.2 写解：`@TEXT('文件名') = 对象列表;`

```lingo
DATA:
   @TEXT('solution.txt') = ROUTES, VOLUME;
ENDDATA
```

适合让 LINGO 自己产出结果文件；但本 Skill 的标准结果输出是 runner 的
CSV 五件套（见 SKILL.md），@TEXT 写文件仅在需要特殊格式时使用。

## 4. 按名取值：`--vars`（免改模型的精确取值通道）

不改模型也能精确拿到任意**变量**的值：runner 用 `LSgetCallbackVarPrimalLng`
按变量名查询：

```
python lingo_runner.py model.lng --vars VOLUME_WH1_C1,X,Y
```

- 名字必须与模型中变量名一致（集合属性成员是 `属性( 成员1, 成员2)` 形式）。
- 查询结果合并进 `variables.csv`（无 reduced_cost 列值）与 stdout JSON。
- 适用：只要少数关键变量的精确值；要全部变量直接读 `variables.csv`。

## 5. 已知限制与进阶

- **字符串输出可行**，官方模式（见 `Programming Samples\VC++\Knapsack\knapsack.lng`）：
  先在 CALC 段把 0-1 解固定，再用**过滤派生集**构造"被选中成员"集合，最后写回指针：
  ```lingo
  SETS:
     ITEMSUSED( ITEMS) | INCLUDE( &1) #GT# .5:;
  ENDSETS
  DATA:
     @POINTER( 5) = ITEMSUSED;   ! 选中成员名列表写回字符串缓冲;
     @POINTER( 6) = @STATUS();
  ENDDATA
  ```
  JSON 对应 `"outputs": {"5": "str", "6": 1}`，runner 返回名字数组。
- 每次求解 runner 都新建/销毁独立的 LINGO 环境（`LScreateEnvLng` →
  `LSdeleteEnvLng`），指针不会跨运行残留。
- `@OLE`/`@ODBC` 依赖本机 Excel/ODBC 驱动，runner 不做封装；
  模型里可直接使用（语法见 `functions.md`），数据文件路径规则同上。
- 模型也可以自带 `SUBMODEL ... ENDSUBMODEL` + `CALC:` 段内 `@SOLVE(...)`
  的自求解结构（如 knapsack.lng）；runner 的脚本 `GO` 仍会执行它，两者不冲突，
  但初学阶段建议保持"模型只建模、脚本负责 GO"的简单分工。
