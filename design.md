# NC (New C) — 语言设计

> 本文件只记录“我们要什么”和 why。标准库 API 见 `stdlib.md`；C/FFI 细节见 `c-interop.md`；实现过程见 `worklog.md`。

## 目标

NC 是“更好的 C”：

- 以 LLVM 为唯一后端。
- 自带构建系统和运行时库。
- 使用 GC 管理内存，不引入所有权或 borrow checker。
- 性能目标是 Go 级别，而不是 C 级零开销。
- 语言保持显式、可预测、容易定位错误。
- 不向前兼容未进入当前设计的旧语法或旧 API。

why：

- C 的主要价值是贴近系统和部署简单；NC 保留这一方向。
- C 的主要痛点是手动内存、头文件模型、隐式规则和工程组织弱；NC 优先解决这些问题。
- 当前项目按 case 驱动，不提前承诺没有真实用例支撑的大能力。

## 架构原则

- case 驱动：每个能力由具体 case 推动。
- 先通后优：链路未通前不优化，链路通了以后立刻自省。
- 多 pass，各司其职：一个 pass 只做一件事。
- LLVM 后端是语言全集和回归权威。
- 遇到未支持语义应明确报错，不做隐式降级。

## 模块

我们要“目录即模块”：

- 模块名由目录名推断。
- 同目录 `.nc` 文件共享命名空间，自动互见。
- 跨模块必须显式 `import`。
- 导入后必须用模块名限定访问：`foo.add()`、`foo.User`。
- `_` 前缀顶层符号是模块私有。
- 标准库模块名由编译器保留，优先于同级用户目录。

why：

- 目录模块比单文件模块更适合真实工程组织。
- 限定访问能避免隐式名字污染。
- `_` 私有规则简单，不引入 `pub/private` 额外语法。

当前边界：

- import v1 只支持一级模块名。
- 不支持包路径、别名导入、选择性导入或单文件模块。

## 可见性

默认公开，`_` 前缀私有。

why：

- 小项目里默认公开更少仪式感。
- 私有命名规则足够直观，也符合当前不增加关键字的取向。

## 类型

我们要一组明确、低魔法的基础类型：

```nc
i8 i16 i32 i64
u8 u16 u32 u64
f32 f64
bool
str
rune
void
*T
?*T
[]T
[N]T
map[K,V]
fun(T) R
```

核心语义：

- `str` 不可变，表示 UTF-8 字节串。
- `rune` 表示 Unicode 码点，不当作普通 numeric 使用。
- `*T` 非空；`?*T` 可为 `nil`。
- `[]T` 是动态切片；`[N]T` 是定长数组。
- `map[K,V]` 是语言内建泛型 map。
- 函数值类型写作 `fun(params) Ret`。

why：

- 指针非空默认能避免 C 式空指针常态化。
- nullable pointer 显式表达风险。
- `rune` 独立于 numeric，避免字符和整数混用。
- 函数类型使用 `fun` 语法，和函数声明保持一致。

## 零值

我们要 Go 式零值：

- 数值为 `0`。
- bool 为 `false`。
- str 为 `""`。
- nullable pointer 为 `nil`。
- slice 为 nil/空切片。
- struct 字段递归零值。
- 非空 `*T` 没有零值，声明时必须初始化。

why：

- 零值让局部初始化和容器默认值更简单。
- 非空指针没有零值，可以让类型系统维护它的承诺。

## 转换

我们要显式转换：

```nc
let x = i64(42)
let s = str(123)
```

核心规则：

- 数值类型之间不做隐式提升。
- 跨数值类型必须显式转换。
- `str(...)` 只支持语言定义的可字符串化类型。
- `size_of(T)` 是语言级编译期内建，返回当前 ABI 下的布局大小。

why：

- C 的隐式提升容易制造隐藏 bug。
- 显式转换让代码生成和错误定位更直接。
- `size_of(T)` 是系统语言刚需，但不需要通用 comptime。

## 变量

变量用 `let` 声明，声明后可重赋值。

```nc
let x: i32 = 5
x = 6
```

我们不要 `const` / `mut` 作为 v1 语言边界。

why：

- 当前优先打通可用语言闭环。
- 不提前设计不可变性系统。

## 函数

我们要：

- 关键字使用 `fun`。
- 单返回值。
- 支持显式 `return`。
- 支持尾表达式返回。
- 支持闭包和函数值。

```nc
fun add(x: i32, y: i32): i32 { x + y }
let f: fun(i32) i32 = fun(x: i32): i32 { x * 2 }
```

why：

- 单返回值降低调用、类型检查和 ABI 复杂度。
- 闭包是现代工程语言的基本能力，但性能目标允许胖指针和间接调用。

## 控制流

我们要表达式化控制流：

- `if` 是表达式。
- `match` 是表达式。
- 条件循环写作 `for condition { ... }`。
- 遍历写作 `for item in items` 或 `for i, item in items`。
- 使用 `break` 跳出循环。

我们不要：

- `while` 关键字。
- `switch` 关键字。

why：

- 控制流少而统一，语法面更小。
- `match` 比 `switch` 更适合后续扩展到 enum、字面量和模式。

## 自定义类型

我们要：

- `struct`。
- `enum`。
- `iface`。
- `type Name = Type` 类型别名。
- 显式泛型 v1，用于函数和 struct。

接口规则：

- struct 自动满足接口，不写 `implements`。
- v1 只采纳指针 receiver 方法。
- 接口值是胖指针。

泛型规则：

- 必须显式写类型实参。
- v1 只有 `any` 约束。
- 实例化后按普通声明检查和生成代码。

why：

- struct/enum 覆盖系统建模的基本需要。
- 接口采用结构化满足，减少声明耦合。
- 显式泛型避免 v1 引入类型推断和复杂约束系统。

## 方法

方法可定义在 struct 上：

```nc
fun (p *Point) move(dx: f64, dy: f64) { ... }
```

我们允许扩展方法，但不允许同名覆盖。

why：

- 方法扩展有利于模块组织。
- 禁止覆盖可保持调用解析简单、稳定。

## 运算符

我们要 C/Go 风格基础运算符，但不继承 C 的隐式数值提升。

核心规则：

- 算术、取模和大小比较要求两侧数值类型一致。
- `%` 只支持整数。
- 指针不参与算术、索引或大小比较。
- 同类型指针只允许 `==` / `!=`。
- 自增/自减是语句，不是表达式。

why：

- 保留熟悉语法。
- 删除 C 中最容易隐藏错误的隐式转换和指针算术。

## 错误处理

我们要 `throw`、`try/catch` 和 `defer`：

```nc
fun load(path: str): str {
    if path == "" { throw "empty path" }
    return fs.read_file(path)
}

try {
    load("config.nc")
} catch e {
    io.println(e)
}
```

核心规则：

- `throw` 不标注异常类型。
- `defer` 按 LIFO 执行。
- `return`、`throw` 和函数正常退出都必须执行已登记 defer。

why：

- v1 需要比错误码更直接的错误传播。
- `defer` 解决资源清理路径分裂问题。
- 不引入 checked exception 或 effect system。

## 内存管理

我们要 GC：

- 用户不手动释放普通 NC 对象。
- 运行时提供显式 `runtime.gc_collect()` 与 `runtime.gc_live()`。
- 当前不承诺后台 GC 或分配时自动触发。

why：

- 目标是减少 C 的生命周期负担。
- 项目仍处在 case 驱动阶段，先保守落地显式 GC，再由真实压力推动自动触发策略。

## 标准库

我们要显式 import 的标准库模块。

当前标准库边界见 `stdlib.md`，包括：

- `io`
- `fs`
- `os`
- `runtime`
- `strings`
- `strconv`
- `math`
- `sort`
- `linux`

why：

- 标准库能力不应伪装成裸语言魔法。
- 显式 import 能让依赖和命名空间清楚。

## FFI

我们要最小 C ABI 互操作：

```nc
extern {
    fun putchar(c: i32): i32
}

extern "m" {
    fun fabs(x: f64): f64
}
```

核心规则：

- extern 只声明外部符号。
- 可选字符串表示链接输入。
- 允许声明级链接符号别名。
- v1 只支持 C ABI scalar/pointer。
- 聚合类型按值传递不进入当前边界。

why：

- 系统语言必须能调用 C。
- 聚合 ABI 在不同 target 上差异大，不能用“看起来能跑”的 lowering 代替真正 ABI 分类。

## 元编程

v1 不引入通用 `comptime`。

当前只接受具体、窄化的编译期能力，例如：

- `size_of(T)`。
- 后续可能的常量表达式。
- 后续可能的 `static_assert`。
- 后续可能的 `cfg` / build config。

why：

- 通用 comptime 会引入编译期执行、副作用、缓存、错误定位和类型生成复杂度。
- 当前还没有 case 证明需要完整 comptime。

## 注释

只支持行注释：

```nc
# comment
```

why：

- 语法简单。
- 不处理块注释嵌套和词法边界问题。

## 构建与目标

我们要自带构建系统：

- `compile` 输出 LLVM IR。
- `build` 输出对象文件、运行时对象和可执行文件。
- 支持显式 target：`windows-x64`、`linux-x64`。

why：

- NC 不应依赖用户手写 make/cmake 才能完成基本构建。
- target 必须显式进入编译模型，FFI 和标准库都依赖它。
