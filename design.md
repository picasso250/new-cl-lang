# NC (New C) — 语言设计文档

> 代号：NC。目标：更好的 C，带 GC，编译到 C，自带构建系统。

## 一、核心定位

| 项 | 决策 |
|-----|------|
| 编译目标 | **编译到 C**，借 C 生态可移植到任意平台 |
| 运行时 | **自带运行时库**（GC），打入生成代码 |
| 性能级别 | **Go 级性能**即可（非 C 级零开销），接受胖指针、间接调用 |
| 调试 | 需做 source map（NC 行号 → 生成的 C 行号） |
| 内存管理 | **GC**（自动管理，不搞所有权 / borrow checker） |
| 构建系统 | **自带**（无需外部 make/cmake） |
| 入口点 | `pub fun main()` —— 程序从 main 函数启动 |
| 标准库 | `print` / `println` 在 `std.io` 中，需 `import std.io` |
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
import http              # 导入 http 模块（目录）
import http { serve }    # 选择性导入
import "net/http"        # 带路径的模块
```

---

## 三、可见性

**默认私有 + `pub` 关键字公开。大小写与可见性无关。**

```nc
fun helper(x: i32): i32 { x + 1 }     # 私有 —— 仅模块内可见

pub fun serve(port: i32) { ... }      # 公开 —— 外部 import 后可见
```

关键字：**`fun`**（非 `fn`）。

编译到 C 时：
- `pub` → 声明写入 `.h`，实现写入 `.c`
- 私有 → 只在 `.c` 中 `static`，不写入 `.h`

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
*T                          # 指针（可为 nil，nil deref = panic）
[]T                         # 切片（动态数组）
[T; N]                      # 定长数组
```

### 4.2 运行时布局

| 类型 | C 层面布局 |
|------|-----------|
| `str` | `{ u8* ptr; u64 len }` |
| `[]T` | `{ T* ptr; u64 len; u64 cap }` |
| `[T; N]` | 内联在 struct/栈中，如 C 数组 |
| `*T` | 单个指针（可为 nil） |
| 接口值 | `{ type* vtable; void* data }` 胖指针 |

### 4.3 零值（Go 式）

| 类型 | 零值 |
|------|------|
| i8~i64, u8~u64 | `0` |
| f32, f64 | `0.0` |
| bool | `false` |
| str | `""` |
| *T | `nil` |
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

### 4.6 类型别名

```nc
type ID = u64
type Point = struct { x: f64, y: f64 }
```

---

## 五、变量

**无 `const` 关键字。`let` = 不可变，`let mut` = 可变。**

```nc
let x: i32 = 5         # 不可变
let mut y: u64 = 0     # 可变
y = 42

let MAX = 256          # 编译期常量（let 初始值为编译期已知量）
```

**顶层变量**：禁止跨模块使用。模块内顶层变量仅本模块可见（即使标 `pub` 也不跨模块，`pub` 仅作用于函数/类型/常量）。

---

## 六、函数

**单返回值。无多返回值。**

```nc
fun add(x: i32, y: i32): i32 { return x + y }
fun greet(name: str) { print("Hello, {name}") }

# 闭包
let twice = fun(x: i32): i32 { x * 2 }
```

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
while i < 10 { i++ }
for item in items { ... }
for i, item in items { ... }
loop { if done { break } }
switch x {
    0           -> ...
    1, 2, 3     -> ...
    4..=10      -> ...
    if x > 100  -> ...
    else        -> ...
}
```

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
    print("error: {e}")
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
| 空指针 | `*T` 可为 `nil`，nil deref → panic + 栈回溯 |
| 指针类型 | 仅 `*T`，不设 `*const T` |
| 方法定义 | 任意模块可扩展，不可重名 |
| 顶层变量 | 禁止跨模块使用 |
