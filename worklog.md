# worklog

## 2026-05-16

- 项目初始化。代号：NC（New C）。
- 确定核心方向：编译到 C + 运行时库、Go 级性能、GC、comptime、胖指针泛型。
- 模块系统：目录即模块（无单文件模块）。
- 可见性：默认私有，`pub` 关键字公开，大小写与可见性无关。
- 错误处理：exception 模型。
- 建立 design.md 包含全部已决之策。
- 建立 review.html + server.js 评审系统。
- **第一轮反馈处理**（共 10 份反馈，7 份实质）：
  - `fun` 替代 `fn` 作为函数关键字
  - 模块系统：取消单文件模块，目录即模块
  - 错误处理：throw 不标注异常类型；引入 defer
  - 并发：从语言级降为库级延迟决策（去掉 go/channel/select 关键字）
  - 变量：去掉 const，`let` = 不可变，`let mut` = 可变
  - 函数：放弃多返回值，单返回值
  - nil：Go 式（解引用 nil 则 panic + 栈回溯）
  - 杂项：type ID = u64、字符串插值 OK、溢出 wrapping
- **第二轮反馈**（1 份）：去掉 `*const T`，唯留 `*T`。指针即战场，入场者自承后果。
- **第三轮反馈**（11 份，堵漏项）：
  - 入口点：`pub fun main()`
  - print：标准库 `std.io`，需 import
  - 模块名：目录名自动推断，无需声明
  - 运行时布局：str = `{u8*; u64}`，[]T = `{T*; u64; u64}`（Go 式）
  - 零值：Go 式
  - 运算符：与 C/Go 一致（含复合赋值、++/--）
  - 字面量默认类型：i32 / f64
  - 注释：仅行注释，`#` 开头
  - 类型转换：函数式 `i64(x)`
  - 方法定义：任意模块可扩展，不可重名
  - 顶层变量：禁止跨模块使用
- design.md 重写为 14 章，覆盖全部已决之策。
- **编译器起步**：Python 实现，BDD 驱动。
  - 四模块：lexer / parser / ast / codegen（C 后端）
  - case_001~006：print + 算术运算符 +-*/% 全通
  - case_007：let 变量声明 + 标识符引用，引入语句/表达式分离
  - case_008~010：多变量、mut、变量表达式
  - case_011：if/else + 比较运算符 + 块结构 + 嵌套作用域
  - case_012：while 循环
  - case_013：fun 函数定义 + return + 多参数 + 返回类型
  - parser 含标准递归下降优先级（additive / multiplicative / primary）
- `已处理/` → `processed/`
- case_014：字符串字面量 + print 适配 %s
- case_015：else if 链（零成本，解析器天然支持嵌套）
- case_016：struct 定义 + 字面量 + 字段访问
- case_017：逻辑运算符 && || !  + 完整优先级链
- symtab 瘦身：Pass1 只管函数签名 + struct 定义，变量声明移交 Pass2。去掉硬编码 "i32"
- case_018：enum 标签枚举（甲层），纯标签无数据，`::` 引用
- case_019：switch 分发，`->` 箭头语法，C switch 映射
- case_020：[N]T 定长数组 + 字面量 + 索引 arr[i]（Go 序）

---

## 20-case 自省 (2026-05-16)

### 编译器体格

| 文件 | 行数 | 职责 |
|------|------|------|
| parser.py | 325 | 递归下降，优先级链完整（|| > && > == != < >... > +- > */% > ! > .field/[i] > primary）|
| codegen.py | 201 | C 代码生成，struct/enum 提升至文件作用域 |
| ast.py | 177 | 21 种 AST 节点 |
| lexer.py | 167 | 词法分析，双字符前瞻 |
| symtab.py | 123 | Pass1：仅收函数签名 + struct/enum 类型 |
| typecheck.py | 105 | Pass2：类型推断 + 局部变量声明 |
| __init__.py | 45 | 三 pass 流水线 + gcc/clang 编译 |

### 能力矩阵

| 已就 | 未就（自举相关） |
|------|-------------------|
| ✓ 算术 + 比较 + 逻辑 | ✗ `[]T` 切片（动态数组） |
| ✓ let / let mut / 赋值 | ✗ `for i in 0 .. N` |
| ✓ if / else if / else | ✗ `str` 真布局 `{u8*; u64}` |
| ✓ while | ✗ 文件 IO |
| ✓ fun + return + 参数 | ✗ `*T` 指针 |
| ✓ fun main() | ✗ 类型转换 `i64(x)` |
| ✓ struct + 字面量 + .field | ✗ f32/f64/bool/i8 等 |
| ✓ enum 甲层 + switch | ✗ 模块 / import |
| ✓ [N]T 定长数组 + 索引 | ✗ 复合赋值 += -= |
| ✓ 字符串字面量 | ✗ 类型注解 `let x: i32` |

### 已知伤疤

| # | 伤疤 | 严重度 | 说明 |
|----|------|--------|------|
| A | `str` 映射为 `const char*` | 中 | 设计规定 `{u8* ptr; u64 len}`，当前偷懒 |
| B | `print` 是魔术函数 | 中 | 应在 `std.io` 库，当前特殊判断 |
| C | C 复合字面量无字段名 | 低 | `Point{3,4}` 非 `Point{.x=3,.y=4}` |
| D | 无类型注解语法 | 低 | `let x: i32 = 1` 不可写 |

### 自举差距

自举需：**enum + switch + []T + str真身 + 文件IO + for...in**。

已得 enum + switch + [N]T。尚差三件：`[]T`、`for...in`、`str` 真布局（含文件 IO）。

建议下一步：`for i in 0 .. 10`（遍历数组），再 `[]T` 切片。

---

## 2026-05-17 运行时债

- if-expression lowering 会生成临时变量。若临时变量类型是 `str`、`[]T`、`nc_map`、`*Struct` 等持有 GC 堆指针的类型，目前不会被自动加入 GC root。
- 当前手动 GC 下通常不炸；但若未来 GC 在分配时自动触发，或表达式求值期间出现 `gc_collect()`，临时值可能被过早回收。
- 这不是泄露问题，而是 premature free / dangling pointer 风险。自动 GC 前必须处理。
