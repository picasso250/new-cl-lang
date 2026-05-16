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
  - parser 含标准递归下降优先级（additive / multiplicative / primary）
- `已处理/` → `processed/`
