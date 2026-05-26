# NC (New C) — 语言设计文档

> 代号：NC。目标：更好的 C，带 GC，以 LLVM 为目标后端，自带构建系统。

## 一、核心定位

| 项 | 决策 |
|-----|------|
| 编译目标 | **目标默认后端为 LLVM**；当前迁移期默认仍为 C，LLVM Lite 后端逐步追平 |
| 运行时 | **自带运行时库**（GC）；迁移目标是独立 runtime C ABI，供 LLVM 后端链接 |
| 性能级别 | **Go 级性能**即可（非 C 级零开销），接受胖指针、间接调用 |
| 调试 | 迁移期保留 NC 行号 → 生成产物定位；LLVM 后端后续接 debug metadata |
| 内存管理 | **GC**（自动管理，不搞所有权 / borrow checker） |
| 构建系统 | **自带**（无需外部 make/cmake）；迁移期 C 后端生成 `build/main.c` + exe，LLVM 后端生成 `build/main.ll` + `build/main.obj` + exe |
| 入口点 | `fun main()` —— 程序从 main 函数启动 |
| 标准库 | `println` 在内置一级模块 `io` 中，需 `import io` 后用 `io.println(value)` |
| 并发 | 延迟决策，不走语言级关键字，后续以库函数提供 |

---

## 二、模块系统

**规则：目录即模块。无单文件模块。模块名 = 目录名（自动推断）。**

```
src/
  http/           # 模块 http（目录名即模块名）
    server.nc     
    client.nc     
    internal.nc   # 同目录所有 .nc 文件共享命名空间，自动互见
  json/           # 模块 json（即使只有一个文件，也必须是目录）
    json.nc
  main/           # 入口模块
    main.nc
```

- 同目录 `.nc` 文件**自动共享命名空间**，可直接互调（无需 import）
- 不再有 `http.nc` 这种单文件模块
- 无需 `__init__.py` 标记
- **模块名 = 目录名**，无需在文件顶部声明

```nc
# 导入
import http              # v1：导入同级 http 模块（目录）
import io                # 内置标准模块，不要求存在同级 io/ 目录
```

当前 import v1 边界：

- CLI 目标目录是入口模块目录；`import foo` 解析为入口模块目录的同级 `foo/` 目录。
- 只支持一级模块名：`import foo`。不支持 `import foo.bar`、`import "net/http"`、`import foo { serve }`、别名导入。
- import 只能出现在顶层。
- `io` 是保留的内置标准模块名；`import io` 不走同级目录查找，不参与 import cycle，且优先于真实同级 `io/` 目录。
- 导入模块后，跨模块符号必须命名空间限定访问：`foo.add()`、`foo.User`、`foo.User { ... }`、`new foo.User { ... }`、`foo.Color::Red`。
- 同目录 `.nc` 文件仍自动共享命名空间，无需 import。
- 导入图递归加载；重复 import 只加载一次；import cycle 报错。
- 编译仍生成单个 C 文件；非入口模块顶层 C 符号用模块名前缀降名，例如 `foo.add` → `foo_add`、`foo.User` → `foo_User`。

当前内置标准模块边界：

- `io.println(value)` 是当前唯一落地的标准输出 API，自动追加换行。
- `io.println` 支持输出 `str`、`bool`、有符号整数、无符号整数和浮点数。
- 裸 `print(...)` 不是语言内建，也不向前兼容。
- 其他临时内建函数（如 `len`、`append`、数值转换、GC 测试钩子、文件 IO）尚未迁入标准模块。

当前后端边界：

- 迁移目标：LLVM 成为默认后端；C 后端降为 reference/debug 后端，是否删除需在 LLVM 达标并稳定后再决策。
- 当前默认后端仍是 C：`compile` 输出 C，`build` 输出 `build/main.c` 与 `build/main.exe`。
- 显式 `--backend llvm` 走 LLVM Lite 后端：`compile` 输出 LLVM IR，`build` 输出 `build/main.ll`、`build/main.obj` 与 `build/main.exe`。
- LLVM 后端 v1 当前承诺基础闭环：基础数值/bool 类型、`str` 字面量、数值转换、`len(str)`、`str ==/!=`、定长数组字面量/索引/索引赋值、struct 值类型声明/字面量/字段读写/参数与返回、enum tag/variant/比较、整数/字符串/bool/enum `match` 表达式、block 表达式、算术/比较、`let`、重赋值、函数、显式 `return` 与尾表达式返回、`if`、条件 `for`、range `for i in start..end`、函数调用与 `io.println`。
- LLVM 后端当前使用 MinGW GNU triple `x86_64-w64-windows-gnu` 生成 Windows COFF object，并用 `gcc` 链接。
- C 后端仍是语言全集和回归权威；LLVM 后端不向前兼容未声明支持的节点，遇到未支持语义应明确报错。

LLVM 默认后端达标门槛：

- LLVM 后端通过全部 `test_cases` 正向/错误用例，以及项目级 import/module 测试。
- str、slice、array、struct、enum、match、nullable pointer、closure/function value、defer/throw/try/catch、GC root 保活、runtime helper 链接路径均有 LLVM 覆盖。
- `python nc.py compile <target>`、`python nc.py build <target>` 切到默认 LLVM 后，仍可用 `--backend c` 运行 C 后端回归。
- 若迁移中确认某能力暂时放弃或延期，必须在 worklog/design 中记录放弃点、原因和替代边界。

---

## 三、可见性

**默认公开，`_` 前缀即私有。**

```nc
fun serve(port: i32) { ... }         # 公开 —— 外部 import 后可见
fun _helper(x: i32): i32 { ... }     # 私有 —— 仅模块内可见
```

关键字：**`fun`**（非 `fn`）。

编译到 C 时：
- 公开 → 声明写入 `.h`，实现写入 `.c`
- 私有（`_` 前缀）→ 只在 `.c` 中 `static`，不写入 `.h`

---

## 四、类型系统

### 4.1 基础类型

```
i8  i16  i32  i64          # 有符号整数
u8  u16  u32  u64          # 无符号整数
f32  f64                    # 浮点
bool                        # 布尔
str                         # 字符串（不可变，UTF-8）
rune                        # 单个 Unicode 码点
void                        # 空
*T                          # 非空指针
?*T                         # nullable 指针（可为 nil）
[]T                         # 切片（动态数组）
[N]T                        # 定长数组
```

### 4.2 运行时布局

| 类型 | C 层面布局 |
|------|-----------|
| `str` | `{ u8* ptr; u64 len }` |
| `[]T` | `{ T* ptr; u64 len; u64 cap }` |
| `[N]T` | 内联在 struct/栈中，如 C 数组 |
| `*T` | 单个指针，非空 |
| `?*T` | 单个指针，C 布局同 `*T`，可为 `nil` |
| 接口值 | `{ type* vtable; void* data }` 胖指针 |

切片语义：

- `a[lo:hi]` 总是复制元素，生成新的底层存储；适用于 `str`、`[]T`、`[N]T`。
- 切片结果与原值不共享可变底层数组；对结果做索引赋值或 `append` 不会写回原数组/原切片。
- `[]T.cap` 是当前底层存储容量；切片复制结果的 `cap == len`。

### 4.3 零值（Go 式）

| 类型 | 零值 |
|------|------|
| i8~i64, u8~u64 | `0` |
| f32, f64 | `0.0` |
| bool | `false` |
| str | `""` |
| *T | 无零值，声明时必须初始化为非空表达式 |
| ?*T | `nil` |
| []T | `nil`（空切片） |
| struct | 各字段递归零值 |
| enum | 第一个变体（若为无数据变体）/ 零值（若为有数据变体） |

### 4.4 字面量默认类型

| 字面量 | 默认类型 | 后缀 |
|--------|---------|------|
| `42` | `i32` | `42u8`, `42i64`, `42u64` |
| `3.14` | `f64` | `3.14f32` |
| `true` / `false` | `bool` | — |
| `"hello"` | `str` | — |

### 4.5 类型转换

采用 **函数式** 语法：`目标类型(值)`。

```nc
let x: i64 = i64(42)
let y: u8 = u8(255)
let z: f32 = f32(3.14)
```

### 4.6 nil 与 nullable pointer

- `nil` 是特殊字面量，只能赋给 `?*T`，或与 `?*T` 做 `==` / `!=`。
- `*T` 不可为 `nil`，`new T { ... }` 返回 `*T`。
- `*T` 可隐式赋给 `?*T`；`?*T` 不可隐式赋给 `*T`。
- 字段访问和方法调用只允许在非空指针上做：`p.x`、`p.x = v`、`p.method()` 要求 `p: *T`。
- v1 支持轻量收窄：`if p != nil { ... }` 或 `if nil != p { ... }` 内，`p: ?*T` 临时视为 `*T`。
- 收窄块内禁止给被收窄变量重新赋值，避免 `p = nil; p.x` 这类流分析漏洞。

### 4.7 类型别名

```nc
type ID = u64
type Point = struct { x: f64, y: f64 }
```

---

## 五、变量

**无 `const` / `mut` 关键字。`let` 声明变量，变量可重赋值。**

```nc
let x: i32 = 5
let y: u64 = 0
y = 42

let MAX = 256          # 编译期常量（let 初始值为编译期已知量）
```

`let` 不表达不可变性；它只引入名字。容器内部修改与变量重赋值都允许。

**顶层变量**：禁止跨模块使用。模块内顶层变量仅本模块可见。

---

## 六、函数

**单返回值。无多返回值。**

```nc
fun add(x: i32, y: i32): i32 { return x + y }
import io
fun greet(name: str) { io.println("Hello, {name}") }

fun choose(b: bool): i32 {
    if b { 1 } else { 3 }   # 函数尾表达式作为返回值
}

let x = if cond { 1 } else { 2 }

# 闭包
let twice = fun(x: i32): i32 { x * 2 }
```

`if` 是表达式。带 `else` 时，所有最终分支尾表达式类型必须一致；`else if` 是 `else` 分支继续接一个 `if` 表达式。
不带 `else` 时，隐含空 `else`，整体类型为 `void`，因此 then 分支也必须是 `void`。
普通 block 已可作为表达式：`{ statements; tail_expr }`，其值来自最后一个尾表达式。

### 方法

**可在任意模块为 struct 定义方法，但不可重名（只允许扩展，不允许覆盖）。**

```nc
struct Point { x: f64, y: f64 }

# 同模块或异模块均可
fun (p: Point) dist(): f64 { ... }
# 若已有 dist 方法，再定义同名 → 编译错误
```

---

## 七、运算符

**与 C/Go 一致。**

数值运算不做隐式提升或隐式常量适配。算术、取模和大小比较要求两侧数值类型完全一致；跨数值类型必须显式写 `目标类型(值)`。`%` 仅支持整数类型，不支持浮点。

| 类别 | 运算符 |
|------|--------|
| 算术 | `+` `-` `*` `/` `%` |
| 位运算 | `&` `|` `^` `~` `<<` `>>` |
| 逻辑 | `&&` `||` `!` |
| 比较 | `==` `!=` `<` `>` `<=` `>=` |
| 赋值复合 | `+=` `-=` `*=` `/=` `%=` `&=` `|=` `^=` `<<=` `>>=` |
| 自增/自减 | `++` `--`（语句，非表达式） |

---

## 八、控制流

```nc
if x > 0 { ... } else if x < 0 { ... } else { ... }
for i < 10 { i++ }
for item in items { ... }
for i, item in items { ... }

let label = match color {
    Color::Red   -> "red"
    Color::Green -> "green"
    Color::Blue  -> "blue"
}

let size = match n {
    0    -> "zero"
    1    -> "one"
    else -> "many"
}
```

`match` 是表达式。v1 支持字面量、`Enum::Variant` 和 `else` 分支；所有分支结果类型必须一致。enum match 无 `else` 时必须覆盖全部变体；非 enum match 必须写 `else`。v1 暂不做 enum 数据解构、变量绑定、guard、范围模式。

---

## 九、自定义类型

```nc
struct Point { x: f64, y: f64 }
let p = Point { x: 3.0, y: 4.0 }

enum Color { Red, Green, Blue, RGB(u8, u8, u8), Named(str) }
let c = Color::RGB(255, 128, 0)

# 接口（胖指针）
iface Writer { fun write(data: []u8): i32 }
iface Reader { fun read(buf: []u8): i32 }
iface ReadWriter { Reader; Writer }

# struct 自动满足接口（不显式声明）
fun (f: File) write(data: []u8): i32 { ... }
```

---

## 十、错误处理

**throw 不标注类型。defer 清理（LIFO）。**

```nc
fun read_file(path: str): str {
    if path == "" { throw "empty path" }
    return contents
}

fun process(path: str) {
    let f = open(path)
    defer { f.close() }
    # 无论正常返回还是 throw，defer 都会执行
}

try {
    let data = read_file("config.nc")
} catch e {
    io.println("error: {e}")
}
```

---

## 十一、元编程（comptime）

```nc
comptime fun make_vec(T: type, n: i32): type {
    return struct { data: [n]T, len: i32 }
}

comptime if ARCH == "x86_64" { ... }
comptime assert(size_of(i32) == 4)
```

编译期函数可接收类型为参数。替代 `#define`、`#ifdef`、`#include` guard。

---

## 十二、FFI

```nc
extern fun printf(fmt: *u8, ...)
extern fun malloc(size: u64): *void
extern fun free(ptr: *void)
extern struct stat { st_size: u64; st_mode: u32 }
extern fun stat(path: *u8, buf: *stat): i32
```

因编译到 C，FFI 天然成立。

---

## 十三、注释

**仅行注释，以 `#` 开头。**

```nc
# 这是注释
let x = 5   # 行尾注释
```

无块注释（`/* */`）。

---

## 十四、杂项汇总

| 项 | 决策 |
|-----|------|
| 字符串插值 | `"Hello, {name}"` |
| 数值溢出 | 静默截断（wrapping，如 C） |
| 空指针 | `*T` 非空；`?*T` 可为 `nil`；nullable deref 由类型系统禁止 |
| 指针类型 | `*T` / `?*T`，不设 `*const T` |
| 方法定义 | 任意模块可扩展，不可重名 |
| 顶层变量 | 禁止跨模块使用 |
| `if` 表达式 | 全部 `if` 都是表达式；无 `else` 时类型为 `void`；有 `else` 时分支类型一致 |
| 条件循环 | 使用 `for condition { ... }`，无 `while` 关键字 |
| block 表达式 | `{ statements; tail_expr }`，值来自尾表达式 |
