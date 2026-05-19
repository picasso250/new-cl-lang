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

### 当时能力矩阵

本段只保留 20-case 时的历史截面，不再记录已落地缺口，避免误导后续判断。

| 已就 | 仍未就 / 未确认 |
|------|-----------------|
| ✓ 算术 + 比较 + 逻辑 | ✗ 模块 / import |
| ✓ let / 赋值 | ✗ 标准库化：`print` / 文件 IO 不应是魔术函数 |
| ✓ if / else if / else | ✗ 复合赋值 `+= -= *= ...` |
| ✓ while / fun / return | ✗ 更多数值类型：i8/u8/i16/u16/i64/u64/f32/f64 |
| ✓ struct / enum / switch | ✗ 指针语义仍需系统性压测 |
| ✓ [N]T / []T / str 真布局 | ✗ 自动 GC 前的 root 生命周期仍需压实 |

### 已知伤疤

| # | 伤疤 | 严重度 | 说明 |
|----|------|--------|------|
| B | `print` 是魔术函数 | 中 | 应在 `std.io` 库，当前特殊判断 |
| C | C 复合字面量无字段名 | 低 | `Point{3,4}` 非 `Point{.x=3,.y=4}` |

### 自举差距

20-case 时列出的 `enum + switch + []T + str真身 + 文件IO + for...in` 已基本落地，不再作为当前差距记录。

当前更高风险的差距转为：**模块/import、标准库边界、defer/throw/return 与 GC root 生命周期、source map / 错误定位、代码生成拆分**。

---

## 2026-05-17 运行时债

- if-expression lowering 会生成临时变量。若临时变量类型是 `str`、`[]T`、`nc_map`、`*Struct` 等持有 GC 堆指针的类型，目前不会被自动加入 GC root。
- 当前手动 GC 下通常不炸；但若未来 GC 在分配时自动触发，或表达式求值期间出现 `gc_collect()`，临时值可能被过早回收。
- 这不是泄露问题，而是 premature free / dangling pointer 风险。自动 GC 前必须处理。

---

## 2026-05-19

- case_090~094：补 defer / root 生命周期 / 错误定位保守组。
  - `defer` 延迟到函数退出执行。
  - 多个 `defer` 按 LIFO 执行。
  - `return` / `throw` 路径会先执行已登记 defer。
  - `defer`、`break` 补 span，类型错误和非法 break 能定位到源码行列。
- 激进第一刀：编译输入从单 source 升级为 source set。
  - 新增 `compile_nc_sources_to_c([(filename, source), ...])`。
  - 同目录多 `.nc` 文件合并为一个 module，Pass1/Pass2/codegen 共用原流水线。
  - `nc.py run <dir>`、`nc.py compile <dir>` 支持目录。
  - `nc.py build <file|dir>` 输出 `build/main.c` 与 `build/main.exe`。
  - 新增项目级 fixture：多文件函数调用、多文件 struct 使用。

### 当前边界

- 多文件现在是“同目录自动互见”，还不是 import/module namespace。
- 多文件诊断仍是合并源码行列，尚未升级为 `file:line:col`。
- `defer` 目前按函数级静态登记生成，`if/loop` 内动态注册语义还需专门 case 压测。
