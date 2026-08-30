# LINGO 建模语言规范速查（写模型前必读）

> 目标：让从未写过 LINGO 的会话**一次写出语法正确的模型**。所有规则均从本机
> LINGO 18 的官方样例（`Samples\`、`Hillier\`、`Tran.ltf`）与 985 页用户手册中提炼。
> 写模型时对照本文件；需要某个 @ 函数的确切签名时再查 `functions.md`。

## ⚠️ 0. 先分清两种语言：LINGO ≠ LINDO

| | LINGO 语法（**本 Skill 只用这种**） | LINDO 语法（旧式，勿模仿） |
|---|---|---|
| 文件 | `.lng` 纯文本 | `.ltx`（如 `Hillier\chap03\lind03_Wyndor.ltx`） |
| 集合 | `SETS: ... ENDSETS` | 无 |
| 数据 | `DATA: ... ENDDATA` | 直接把数字写进约束 |
| 目标 | `MIN = @SUM(...);`（**必须有 `=`**） | `MAX 3 X1 + 5 X2`（无 `=`，隐式乘法） |
| 约束标签 | `[Cap]` 方括号 | `Cap)` 圆括号 |
| 整数声明 | `@GIN(x); @BIN(x);` 写在模型里 | `INT n` / `GIN n` 写在 `END` 之后 |

`Hillier\` 目录中 `.ltx` 文件是 LINDO 语法、`.lg4` 内是 LINGO 语法。看到
`SUBJECT TO` 就是 LINDO 语法，**不要**把它混进 LINGO 模型。

---

## 1. 模型骨架

```lingo
MODEL:
! 注释：感叹号开始、分号结束，可跨行;

SETS:
 ! 集合与属性声明，见第 3 节;
ENDSETS

DATA:
 ! 数据块，见第 4 节;
ENDDATA

 ! 目标与约束，见第 5 节;

END
```

- `MODEL:` 和 `END` 包裹模型；单独求解的模型文件两者都要有。
- `SETS:`/`ENDSETS`、`DATA:`/`ENDDATA` 这四个段关键字**本身不带分号**。
- `DATA:` 块可以出现多次（常见模式：开头一块输入数据，结尾一块 `@POINTER` 输出）。
- 关键字大小写不敏感（`MODEL:` 与 `model:` 等价），样例惯用全大写段关键字。

## 2. 基本词法规则

- **每条语句以分号 `;` 结尾**（包括约束和目标）；漏分号是最常见错误。
- 注释：`! 这是注释;`（以 `!` 开始、以 `;` 结束，可跨行）。模型内部没有 `/* */`。
- 关系运算符：`<=`（或 `<`）、`>=`（或 `>`）、`=`。LINGO 不使用 `==`。
- 逻辑运算符（用于条件过滤和 @IF）：`#EQ# #NE# #GT# #GE# #LT# #LE#`、
  `#AND# #OR# #NOT#`。**两侧的 `#` 不能省**。
- 数学运算：`+ - * /`、`^`（乘方）、函数调用一律 `@NAME(args)`。
- 变量默认非负（≥0）。允许负值必须显式 `@FREE(x);`。
- 行长度与字符：纯 ASCII 最稳；模型文件建议 UTF-8 无 BOM 或 ANSI。
  **中文只能出现在注释里**，不要用于集合成员名、变量名。
- **单行长度上限（实测）**：任何一行超过约 **800 字符**会触发 Error 3
  "Overlength line"，且该行数据被截断——矩阵数据务必按每行 ≤500 字符分块
  折行（Python 生成模式见第 4.1 节）。

## 3. SETS 段：集合与属性

### 3.1 原始集（primitive set）

```lingo
SETS:
   WAREHOUSE / WH1, WH2, WH3/   : CAPACITY;   ! 成员显式列出;
   CUSTOMER  / C1..C4/          : DEMAND;     ! .. 范围省略（成员为 C1 C2 C3 C4）;
   DAYS      / MON..SUN/        : NEEDS, START;  ! 一个集合可挂多个属性;
ENDSETS
```

- 语法：`集合名 / 成员列表/ : 属性1, 属性2;`
- 成员名是**字符串标签**（`WH1`、`MON`…）或数字。成员列表为空（`/ /`）时，
  成员由 DATA 段或 `@POINTER` 运行时给出（见 `data_bridge.md`）。

### 3.2 派生集（derived set）——建模的主力

```lingo
SETS:
   WAREHOUSE / WH1, WH2, WH3/ : CAPACITY;
   CUSTOMER  / C1, C2, C3, C4/: DEMAND;
   ROUTES( WAREHOUSE, CUSTOMER) : COST, VOLUME;   ! 3×4=12 个成员的笛卡尔积;
ENDSETS
```

- `ROUTES(I,J)` 同时携带 `COST`、`VOLUME` 两个属性——对应运输问题矩阵。
- 稀疏派生集（只要部分组合）：
  ```lingo
  ! 方式一：显式列举成员组合;
  LINKS( WAREHOUSE, CUSTOMER) / WH1,C1  WH1,C3  WH2,C2/ : COST, VOLUME;
  ! 方式二： membership filter（由父集元素的条件决定）;
  ARC( NODE, NODE) | &1 #LT# &2 : FLOW;   ! &1、&2 是父集索引的占位;
  ```

## 4. DATA 段：给属性赋值

```lingo
DATA:
   CAPACITY = 30 25 21;              ! 按集合成员顺序一维列出;
   DEMAND   = 15 17 22 12;
   COST     =  6  2  6  7            ! 矩阵按第一个索引逐行排列;
               4  9  5  3            ! 行内可加 ! 注释;
               8  8  1  5;
ENDDATA
```

- 逗号与空格都可作为分隔符（`30, 25, 21` 等价 `30 25 21`）。
- 也可以在集合声明时就内联成员（`WAREHOUSE / WH1, WH2, WH3/`），数据只给属性。
- 数据也可以来自文件/Excel/ODBC：`@TEXT('data.txt')`、`@OLE('b.xlsx')`、
  `@ODBC(...)`、`@POINTER(n)`——见 `data_bridge.md`。

### 4.1 超长矩阵数据的分块书写（实测必用）

单行超过约 800 字符触发 Error 3 "Overlength line" 且数据被截断。Python 生成
`.lng` 时按字符数折行：

```python
def fmt_data(vals, per_line=500):
    """把展平的矩阵数据折成多行，每行不超过 per_line 个字符。"""
    lines, cur = [], ""
    for v in vals:
        s = " %.10g" % v
        if len(cur) + len(s) > per_line:
            lines.append(cur)
            cur = ""
        cur += s
    if cur:
        lines.append(cur)
    return "\n".join(lines)

# DATA:
#  S = <fmt_data(flat_matrix)>;
# ENDDATA
```

另注意内联数据**总量**：MB 级（实测 1.3 MB）会触发 Error 62
"Ran out of workspace in model generation"——模型根本没进入求解，runner 状态为
NOT SOLVED。此时把数据外置（`@TEXT`/`@POINTER`，见 `data_bridge.md`）或缩减规模；
判断"模型没跑"看 `lingo_run.log` 末尾的 `[Error Code: N]` 行。

## 5. 目标与约束

```lingo
! 目标：MIN = 或 MAX = （必须有等号）;
 [OBJ] MIN = @SUM( ROUTES( I, J): COST( I, J) * VOLUME( I, J));

! 约束：@FOR 对集合每个成员生成一条约束;
 @FOR( CUSTOMER( J): [DEM]
    @SUM( WAREHOUSE( I): VOLUME( I, J)) >= DEMAND( J));
 @FOR( WAREHOUSE( I): [SUP]
    @SUM( CUSTOMER( J): VOLUME( I, J)) <= CAPACITY( I));
```

- `[OBJ]`、`[DEM]`、`[SUP]` 是**行标签**：出现在求解报告和
  `constraints.csv` 的 row_name 列里，强烈建议给每类约束起名。
- 集合函数语法：`@SUM( 集合( 索引1, 索引2): 表达式)`、
  `@FOR( 集合( 索引): 语句1; 语句2; ...)`（@FOR 体内多条语句用分号隔开，
  整体以分号结束）。
- 简单模型可以不用集合，直接写标量约束：
  ```lingo
  MODEL:
   [OBJ] MAX = 3*X + 2*Y;
    [P1] X <= 10;
    [P2] Y <= 8;
    [P3] X + Y <= 16;
  END
  ```

### 5.1 变量域声明（写在约束区，每条以分号结束）

```lingo
 @GIN( N);            ! 一般整数（…,-2,-1,0,1,2,…）;
 @BIN( OPEN( I));     ! 0-1 变量（可对属性逐成员声明）;
 @FREE( X);           ! 允许取负（默认变量非负）;
 @BND( 5, X, 20);     ! 下界 5 ≤ X ≤ 20（比约束更高效，优先用）;
 @SEMIC( 1, X, 10);   ! X=0 或 1≤X≤10;
```

**防御性 @BND（实测规则）**：凡作 0-1 松展或有界语义使用的集合属性，用
`@BND( 0, X, 1)` 把**上下界都写全**，不要依赖"默认非负 + 条件门控约束"。
实测踩坑：某下界模型给变量 Z 写了 `@BND(0, Z, 1)`，却漏掉同为 0-1 语义的
SB/SE，只靠 `@FOR` 条件约束门控——松展模型因此留有语义漏洞。`lingo_runner.py`
会在求解前对"已声明部分变量域、但仍有属性缺域"的模型给出 advisory 提示。

## 6. 高频正确模式（照抄结构即可）

### 6.1 条件过滤 `|`（筛选集合成员）

```lingo
 @SUM( LINKS( I, J) | I #NE# J: COST( I, J) * X( I, J))  ! 排除自身;
 @SUM( DAYS( D) | D #LE# 5: START( @WRAP( TODAY - D + 1, @SIZE( DAYS))))
```

### 6.2 环形/周期索引：`@WRAP( k, n)` 把任意整数折回 `[1, n]`

```lingo
! 排班问题：今天当班的人 = 最近 5 天内开始的人（星期天回卷到星期一）;
@FOR( DAYS( TODAY):
    ONDUTY( TODAY) = @SUM( DAYS( D)| D #LE# 5:
        START( @WRAP( TODAY - D + 1, @SIZE( DAYS))));
```

### 6.3 分段/非线性目标函数：`@IF( cond, then, else)`

```lingo
 COSTX = @IF( X #LE# 100, 5*X, 5*100 + 3*(X - 100));   ! 阶梯价格;
```

### 6.4 0-1 建模套路（固定成本/开闭）

```lingo
! 只有选中 Y(j)=1 时才能生产：X 上界乘指示变量;
 X( I, J) <= SALES( J) * Y( J);
 @BIN( Y( J));
```

## 7. 高频错误自查清单（提交前逐条自查）

1. **漏分号**——每条语句（含目标、每条约束、每个 @GIN）都必须以 `;` 结尾；
   反过来 `SETS:`/`DATA:` 段关键字后**不能**加分号。
2. **目标忘了 `=`**：写成 `MIN @SUM(...)`；必须 `MIN = @SUM(...)`。
3. **把 LINDO 语法混进来**：`SUBJECT TO`、`Row)` 标签、隐式乘法 `3 X1`。
4. **注释没有以 `;` 结束**：`! 说明`（缺分号会把下一句吞掉）。
5. **派生集属性当集合用**：`@SUM( COST( I, J): ...)` 错；应 `@SUM( ROUTES( I, J): COST( I, J) ...)`。
6. **索引字母未声明就使用**：`( I, J)` 必须出现在集合函数的集合引用里，不能凭空出现。
7. **矩阵数据行列数与集合尺寸不符**：COST 是 |WAREHOUSE|×|CUSTOMER| 个数，
   按第一个索引逐行排列。
8. **忘了变量默认非负**：需要负值/无约束变量时漏 `@FREE`。
9. **在 DATA 段里写约束**，或在段关键字后面加分号——段结构要完整闭合。
10. **成员名用了中文或带空格**：成员名/变量名只能是字母数字下划线。
11. **行标签与已有名字重名**（Error 37 "Name already in use"）：`[CAP]` 这类
    标签与集合/属性/变量共享命名空间——若集合里已有属性 `CAP`，行标签必须
    换名（如 `[PLANTCAP]`）。
12. **DATA/约束单行超长（>约 800 字符）**：Error 3 "Overlength line"，超长行
    数据被截断——按每行 ≤500 字符分块折行（模式见第 4.1 节）。
13. **内联 DATA 总量过大（MB 级，实测 1.3 MB）**：Error 62 "Ran out of
    workspace in model generation"，模型未进入求解（runner 状态 NOT SOLVED），
    并非不可行——数据外置（@TEXT/@POINTER）或缩减规模，读 `lingo_run.log`
    末尾的 Error 行确认。
14. **0-1/有界语义漏写 @BND**：只依赖"默认非负 + 条件门控约束"会留语义
    漏洞——显式 `@BND( 0, X, 1)` 双界写全（见第 5.1 节防御性 @BND）。

## 8. 完整模板（三个）

`assets/templates/` 下有三个可直接改写使用的模板（与下面相同）：

1. `transport_sets.lng` —— SETS/DATA 运输问题（LP，线性）。
2. `integer_program.lng` —— 0-1 混合整数规划（@BIN + 指示变量）。
3. `pointer_bridge.lng` —— @POINTER 数据桥接（Python 传数组进出）。

模型写完后：用 `scripts/lingo_runner.py 模型文件` 求解（工作流见 SKILL.md）。
求解器会指出第一个语法错误所在的行号（`lingo_run.log` 中 `[Error Code: N]`），
修正后重跑即可——但按本文件写，通常一次通过。
