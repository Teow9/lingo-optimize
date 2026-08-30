# LINGO 内置函数速查（精选 113 / 共 270）

> 来源：本机 `Notepad++\src\LINGO.xml`（LINGO 18 官方自动补全定义，914 词条）与用户手册。
> 说明列摘自官方描述（英文原文，保真优先）；带 ★ 的函数附示例。
> 全量清单可在 `E:\Tools\LINGO64_18\Notepad++\src\LINGO.xml` 检索，或查用户手册（`Lingo_18_Users_Manual.chm`，可全文检索）。


## 集合与聚合（建模主力）

| 函数 | 参数 | 说明 |
|---|---|---|
| ★ `@SUM` | `(setname[(set_index_list)[|cond_qualifier]]:expression)` | Return the sum of an expression over the setname set |
| ★ `@FOR` | `(setname[(set_index_list)[|cond_qualifier]]:exp_list)` | Generate the expressions contained in exp_list for all members of the setname set |
| `@MAX` | `(setname[(set_index_list)[|cond_qualifier]]:expression)` | Find the maximum of an expression over members of a set |
| `@MIN` | `(setname[(set_index_list)[|cond_qualifier]]:expression)` | Find the minimum of an expression over members of a set |
| `@PROD` | `(setname[(set_index_list)[|cond_qualifier]]:expression)` | Return the product of an expression over the setname set |
| `@SIZE` | `(set_name)` | Return the size of a set |
| `@CARD` | `('card_set_name', variable|n)` | Restrict that at most N of the variables in the set to be nonzero(i.e. cardinality) |
| `@IN` | `(set_name, primitive_1_index[,primitive_2_index,...])` | Determine if a set element is contained in a set |
| `@INDEX` | `(set_name, set_member)` | Return the index of a set element within its set |
| ★ `@WRAP` | `(index, limit)` | Return j such that j = index - k * limit, where k is an integer and j in [1,limit] |

示例：
```lingo
@SUM( ROUTES( I, J): COST( I, J) * VOLUME( I, J))   ! 对派生集逐元素求和;
@FOR( WAREHOUSE( I): @SUM( CUSTOMER( J): VOLUME( I, J)) <= CAPACITY( I));   ! 为每个成员生成一条约束;
START( @WRAP( TODAY - D + 1, @SIZE( DAYS)))   ! 环形索引：把任意整数折回 [1, n];
```

## 变量域与整数声明

| 函数 | 参数 | 说明 |
|---|---|---|
| ★ `@GIN` | `(variable)` | Restrict variable to general integer values |
| ★ `@BIN` | `(variable)` | Restrict variable to be a binary value |
| ★ `@FREE` | `(variable)` | Allow variable to take any positive or negative value |
| ★ `@BND` | `(lower_bound, variable, upper_bound)` | Limit variable to being in range of [lower_bound, upper_bound] |
| `@SEMIC` | `(lower_bound, variable, upper_bound)` | Restrict variable to being either 0 or in the range of [lower_bound, upperbound] |
| `@ALLDIFF` | `('set_name', variable_name)` | Mark a set of general integers to take different values |

示例：
```lingo
@GIN( N);   ! N 为一般整数;
@BIN( OPEN( I));   ! 0-1 变量;
@FREE( X);   ! 变量默认 >= 0，此函数解除限制;
@BND( 5, X, 20);   ! 5 <= X <= 20，比写约束更高效;
```

## 数学函数

| 函数 | 参数 | 说明 |
|---|---|---|
| `@ABS` | `(x)` | Return the absolute value of x |
| `@EXP` | `(x)` | Return natural exponential of x |
| `@LOG` | `(x)` | Return the natural logarithm of x |
| `@LOG10` | `(x)` | Return the base 10 logarithm of x |
| `@SQR` | `(x)` | Return the value of x squared |
| `@SQRT` | `(x)` | Return the square root of x |
| `@POW` | `(x, y)` | Return the value of x raised to the y power |
| `@MOD` | `(x, y)` | Return the remainder of an integer divide of x by y |
| `@INT` | `(x)` | Return the largest integer that less than x |
| `@FLOOR` | `(x)` | Return the integer part of x |
| `@ROUND` | `(x, n)` | Round x to the closest number to x having n digits |
| `@ROUNDUP` | `(x, n)` | Round x up(away from 0) to the closest number to x having n digits |
| `@ROUNDDOWN` | `(x, n)` | Round x down(towards 0) to the closest number to x having n digits |
| `@SIGN` | `(x)` | — |
| `@SMAX` | `(x1, x2, ..., xn)` | Return the maximum value of x1, x2,..., and xn |
| `@SMIN` | `(x1, x2, ..., xn)` | Return the minimum value of x1, x2,..., and xn |
| `@PI` | `()` | Return the value of 'Pi' |
| `@SIN` | `(x)` | Return the sine of x, where x is the angle in radians |
| `@COS` | `(x)` | Return the cosine of x, where x is an angle in radians |
| `@TAN` | `(x)` | Return the tangent of x, where x is the angle in radians |
| `@ASIN` | `(x)` | Return the inverse sine of x, where x is an angle in radians |
| `@ACOS` | `(x)` | Return the inverse cosine of x, where x is an angle in radians |
| `@ATAN` | `(x)` | Return the inverse tangent of x, where x is an angle in radians |
| `@ATAN2` | `(x, y)` | Return the inverse tangent of y/x |
| `@SINH` | `(x)` | Return the hyperbolic sine of x, where x is the angle in radians |
| `@COSH` | `(x)` | Return the hyperbolic cosine of x, where x is an angle in radians |
| `@TANH` | `(x)` | Return the hyperbolic tangent of x, where x is an angle in radians |

## 条件与流程（计算段）

| 函数 | 参数 | 说明 |
|---|---|---|
| ★ `@IF` | `(logical_condition, true_result, false_result)` | Evaluate logical_condition, if true, returns true_result, otherwise returns false_result |
| `@IFC` | `(conditional_exp:statement_1[;...;statement_n;] [@ELSE statement_1[;...;statement_n;]])` | Provide conditional if/then/else branching capabilities |
| `@ELSE` | `(statement_1[;...;statement_n;])` | Provide conditional IF/THEN/ELSE branching capabilities |
| `@WHILE` | `(conditional_exp:statement_1[;...;statement_n;])` | Loop over a group of statements until some termination criterion is met |
| `@STOP` | `('message')` | Terminate execution of the current model |
| `@PAUSE` | `('text1'|value1[,...,'textn'|valuen])` | Pause execution and wait for a user response |

示例：
```lingo
@IF( X #LE# 100, 5*X, 500 + 3*(X-100))   ! 条件取值（分段价格）;
```

## 概率分布（@P<分布>CDF/PDF/INV 家族，数模常用）

| 函数 | 参数 | 说明 |
|---|---|---|
| `@PNORMCDF` | `(mu, sigma, x)` | The normal cumulative distribution |
| `@PNORMPDF` | `(mu, sigma, x)` | The normal probability distribution |
| `@PNORMINV` | `(mu, sigma, x)` | The inverse of normal cumulative distribution |
| `@PSN` | `(x)` | The standard normal cumulative distribution, being replaced by @PNORMCDF |
| `@PPOISCDF` | `(lambda, x)` | The poisson cumulative distribution |
| `@PPOISPDF` | `(lambda, x)` | The poisson probability distribution |
| `@PPOISINV` | `(lambda, x)` | The inverse of poisson cumulative distribution |
| `@PBINOCDF` | `(n_trials, prob_success, x)` | The binomial cumulative distribution |
| `@PBINOPDF` | `(n_trials, prob_success, x)` | The binomial probability distribution |
| `@PBINOINV` | `(n_trials, prob_success, x)` | The inverse of binomial cumulative distribution |
| `@PBN` | `(p_defective, n_samples, x)` | The cumulative binomial probability, being replaced by @PBINOCDF |
| `@PUNIFCDF` | `(lower, upper, x)` | The uniform cumulative distribution |
| `@PUNIFPDF` | `(lower, upper, x)` | The uniform probability distribution |
| `@PUNIFINV` | `(lower, upper, x)` | The inverse of uniform cumulative distribution |
| `@PEXPOCDF` | `(lambda, x)` | The exponential cumulative distribution |
| `@PEXPOPDF` | `(lambda, x)` | The exponential probability distribution |
| `@PEXPOINV` | `(lambda, x)` | The inverse of exponential cumulative distribution |
| `@PTRIACDF` | `(lower, upper, mode, x)` | The triangular cumulative distribution |
| `@PTRIAINV` | `(lower, upper, mode, x)` | The inverse of triangular cumulative distribution |
| `@PTRIAPDF` | `(lower, upper, mode, x)` | The triangular probability distribution |
| `@PGAMMCDF` | `(scale, shape, x)` | The gamma cumulative distribution |
| `@PGAMMPDF` | `(scale, shape, x)` | The gamma probability distribution |
| `@PWEIBCDF` | `(scale, shape, x)` | The weibull cumulative distribution |
| `@PLOGNCDF` | `(mu, sigma, x)` | The lognormal cumulative distribution |
| `@PLGSTCDF` | `(location, scale, x)` | The logistic cumulative distribution |
| `@PGEOMCDF` | `(prob_success, x)` | The geometric cumulative distribution |
| `@PCHISCDF` | `(deg_freedom, x)` | The chi-square cumulative distribution |
| `@PSTUTCDF` | `(deg_freedom, x)` | The student's t cumulative distribution |
| `@PBETACDF` | `(alpha, beta, x)` | The beta cumulative distribution |
| `@PLAPLCDF` | `(location, scale, x)` | The laplace cumulative distribution |
| `@PHYPGCDF` | `(n_population, d_num_defective, k_sample_size, x)` | The hypergeometric cumulative distribution |
| `@PNEGBPDF` | `(r_num_failures, p_prob_success, x)` | The negative binomial probability distribution |

## 随机数与模拟

| 函数 | 参数 | 说明 |
|---|---|---|
| `@RAND` | `(seed)` | Return a pseudo-random number between 0 and 1 depending deterministically on seed |
| ★ `@QRAND` | `(seed)` | Produce a sequence of 'quasi-random' uniform numbers in the interval (0,1) |
| `@SPSTGRNDV` | `(stage, variable_name)` | Identify the random variables in a CCP model |

示例：
```lingo
@QRAND( 1)   ! 准随机均匀序列(0,1)，蒙特卡洛用;
```

## 统计与拟合

| 函数 | 参数 | 说明 |
|---|---|---|
| ★ `@REGRESS` | `(y, x)` | Multiple linear regression |
| `@SPMEAN` | `(variable|row)` | Determine the mean value across all scenarios for any specified variable or row name |
| `@SPSTDDEV` | `(variable|row)` | Determine the standard deviation of any variable or row across all scenarios |
| `@SPCORRPEARSON` | `(random_var_1, random_var_2, rho)` | Induce correlations between two random variables, method is 'pearson' |
| `@SPMAX` | `(variable|row)` | Determine the maximum value across all scenarios for any specified variable or row name |
| `@SPMIN` | `(variable|row)` | Determine the minimum value across all scenarios for any specified variable or row name |
| `@NORMSINV` | `(probability)` | The inverse of the standard normal cumulative distribution |
| `@NORMINV` | `(probability, mu, sigma)` | The inverse of the normal cumulative distribution, being replaced by @PNORMINV |

示例：
```lingo
! 在计算段做多元线性回归: CALC: @REGRESS(X1,X2,Y,BETA); ENDCALC;
```

## 线性代数与矩阵

| 函数 | 参数 | 说明 |
|---|---|---|
| `@TRANSPOSE` | `(a)` | Return the transpose of the matrix a |
| `@INVERSE` | `(a)` | Return the inverse of the matrix a |
| `@DETERMINANT` | `(a)` | Calculate determinant value for matrix a |
| `@MTXMUL` | `(b, c)` | Return the result of matrix b multiples matrix c |
| `@CHOLESKY` | `(a)` | Cholesky factorization of the symmetric, positive definite matrix a |
| `@EIGEN` | `(a)` | Calculate eigenvectors and eigenvalues for the matrix a |
| `@POSD` | `(matrix)` | Specify a matrix of decision variables to be positive semi-definite |
| `@QRFACTOR` | `(a)` | Return QR factorization of matrix a |
| `@RANK` | `(attribute_to_be_ranked)` | Rank the values of an attribute in ascending order |
| `@SORT` | `(set|attribute(s))` | Return the ordering of the set members or attributes |
| `@BLOCKROW` | `(block_index, row_name)` | Assign rows to their respective blocks, used in conjunction with BNP solver |

## 数据输入输出

| 函数 | 参数 | 说明 |
|---|---|---|
| ★ `@TEXT` | `([['filename'],'a'])` | Export solutions to text files |
| ★ `@WRITE` | `('text1'|value1[,...,'textn'|valuen])` | Output one or more objects |
| `@WRITEFOR` | `(setname[(set_index_list)[|cond_qualifier]]:'text1'|value1[,...,'textn'|valuen])` | Output multiple objects in a set that met some conditional qualifier |
| `@FORMAT` | `(value, format_descriptor)` | Format a numeric or string value for output as text |
| `@FILE` | `('filename')` | Include data from external text files |
| `@NEWLINE` | `(n)` | Write n new lines to the output device |
| `@STRLEN` | `(string)` | Get the length of a specified string |
| `@ODBC` | `(['data_source'[,'table_name'[,'col_1'[,'col_2',...]]]])` | Import data from and export data to any ODBC data source, Windows platform only |
| `@OLE` | `(['workbook_file'][,range_name_list])` | Move data and solutions back and forth from Excel using OLE based transfers |
| ★ `@POINTER` | `(n)` | Transfer data directly through shared memory locations |
| `@DIVERT` | `(['filename'[,'a']])` | Divert outputs to file, 'a' means append, default action is overwrite |

示例：
```lingo
DATA:  @TEXT('result.txt') = ROUTES, VOLUME;  ENDDATA   ! 把解写入文本文件;
@WRITE( 'profit=', OBJ)   ! 输出文本与数值;
DATA:  X = @POINTER( 1);  @POINTER( 2) = OBJ;  ENDDATA   ! 与宿主程序共享内存传数;
```

## 求解控制与求解信息

| 函数 | 参数 | 说明 |
|---|---|---|
| `@SOLVE` | `([submodel_name[,...,submodel_name_n]])` | Solve one or multiple submodels |
| `@GEN` | `([submodel_name[,...,submodel_name_n]])` | Generate a model and display the generated expressions |
| `@GENDUAL` | `([submodel_name[,...,submodel_name_n]])` | Generate the dual formulation of a linear model and display the generated expressions |
| ★ `@STATUS` | `()` | Return the final status of the solution process |
| `@ITERS` | `()` | Return the total number of iterations required to solve the model |
| `@OBJBND` | `()` | Return the bound on the objective value |
| `@DUAL` | `(variable_or_row_name)` | Output the dual value of a variable or a row |
| `@RANGED` | `(variable_or_row_name)` | Output the allowable decrease on a specified variable's objective coefficient or on a specified row's right-hand side |
| `@RANGEU` | `(variable_or_row_name)` | Output the allowable increase on a specified variable's objective coefficient or on a specified row's right-hand side |
| `@SET` | `('param_name', parameter_value)` | Change a parameter's setting |
| `@DEBUG` | `([submodel_name[,...,submodel_name_n]])` | Debug one or multiple submodels |
| `@SOLU` | `([0|1[,model_object[,'report_header']]])` | Display nonzero variables and binding rows only if 0, all information if 1 |
| `@NEXTKBEST` | `()` | Find the next best solution of binary integer model |

示例：
```lingo
@POINTER( 9) = @STATUS();   ! 0=全局最优 6=局部最优 1=不可行 2=无界;
```

## 备注

- `@P<分布>CDF/PDF/INV` 是一整套分布族：BETA(贝塔)、BINO(二项)、CAUCY(柯西)、CHISQ(卡方)、EXPO(指数)、FDST(F)、GAMM(伽马)、GEOM(几何)、GMBL(冈贝尔)、HYPG(超几何)、LAPL(拉普拉斯)、LGST(逻辑斯蒂)、LOGN(对数正态)、LOGR、NEGB(负二项)、NORM(正态)、PRTO(帕累托)、SMST、STUT(t)、TRIA(三角)、UNIF(均匀)、WEIB(威布尔)。后缀 `CDF`=累积分布、`PDF`=密度、`INV`=分位数/反函数。旧短名（如 `PSN`=正态CDF、`PBN`=二项CDF、`PFD`=F分布CDF、`PPL`/`PFS`/`PEB`/`PEL`/`PCX`/`PHG`/`PIC`/`PSL`/`PTD`/`PPS`）仍可用但已被长名替代。
- `@SP*` 是情景/蒙特卡洛管理函数族（SPSAMPLING、SPNUMSCENE、SPCHANCE、SPDIST*…），随机规划高级用法见手册。
- `@CHART*` 生成 LINGO 自带图表；本 Skill 的绘图统一走 Python（读 runner 输出的 CSV）。
- 计算段（`CALC: ... ENDCALC`）可在建模前做数据处理（@IFC/@WHILE/@REGRESS 等流程函数主要在此使用）。
