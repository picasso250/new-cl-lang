# NC (New C) — 语言设计文档

> 代号：NC。目标：更好的 C，带 GC，以 LLVM 为目标后端，自带构建系统。

## 一、核心定位

| 项 | 决策 |
|-----|------|
| 编译目标 | **LLVM** 是唯一后端 |
| 运行时 | **自带运行时库**（GC）；LLVM 后端链接由 `runtime/ncrt.c` 编译出的静态对象 |
| 性能级别 | **Go 级性能**即可（非 C 级零开销），接受胖指针、间接调用 |
| 调试 | 迁移期保留 NC 行号 → 生成产物定位；LLVM 后端后续接 debug metadata |
| 内存管理 | **GC**（自动管理，不搞所有权 / borrow checker） |
| 构建系统 | **自带**（无需外部 make/cmake）；生成 `build/main.ll`、`build/main.obj`、`build/ncrt.obj` 与 exe |
| 入口点 | `fun main()` —— 程序从 main 函数启动 |
| 标准库 | 内置一级模块 v1：`io`、`fs`、`runtime`；需显式 `import` 后用限定名访问 |
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
- `io`、`fs` 与 `runtime` 是保留的内置标准模块名；`import io` / `import fs` / `import runtime` 不走同级目录查找，不参与 import cycle，且优先于真实同级目录。
- 导入模块后，跨模块符号必须命名空间限定访问：`foo.add()`、`foo.User`、`foo.User { ... }`、`new foo.User { ... }`、`foo.Color::Red`。
- 同目录 `.nc` 文件仍自动共享命名空间，无需 import。
- 导入图递归加载；重复 import 只加载一次；import cycle 报错。
- 编译生成单个 LLVM module；非入口模块顶层符号用模块名前缀降名，例如 `foo.add` → `foo_add`、`foo.User` → `foo_User`。

当前内置标准模块边界：

- `io.print(value)` / `io.println(value)` 是当前落地的标准输出 API；`println` 自动追加换行，`print` 不追加换行。
- `fs.read_file(path)` / `fs.write_file(path, content)` 是当前唯一落地的文件 IO API；读写失败会 `throw` 字符串错误。
- `runtime.gc_collect()` 与 `runtime.gc_live()` 是当前唯一公开的运行时调试 API；裸 `gc_collect()` / `gc_live()` 不再是 builtin。
- `io.print` / `io.println` 支持输出 `str`、`rune`、`bool`、有符号整数、无符号整数和浮点数；`rune` 按对应 UTF-8 字符输出，不输出数字码点。
- 裸 `print(...)` 不是语言内建，也不向前兼容。
- `len`、`append`、数值转换和 `map_has` 仍是语言级内建；`map[K,V]` 是内建泛型 map 类型。

当前后端边界：

- LLVM 是唯一后端：`compile` 输出 LLVM IR，`build` 输出 `build/main.ll`、`build/main.obj`、`build/ncrt.obj` 与 `build/main.exe`。
- `--backend` 入口已删除；显式传入 `--backend` 会报错。旧 C 后端和旧 `compile_nc_to_c` / `run_c_code` / `build_c_code` API 不保留向前兼容。
- LLVM 后端 v1 当前承诺基础闭环：基础数值/bool 类型、`str` 字面量/索引/切片/拼接、数值转换、`str(i32)`、`i32(str)`、`len(str)`、`str ==/!=`、定长数组字面量/索引/索引赋值、slice layout/literal/index/`len`/`append`、定长数组与 slice 切片复制、slice `for i, item in s`、struct 值类型声明/字面量/字段读写/参数与返回、heap struct `new`、指针 receiver 方法声明/调用、nullable pointer `nil`/`!= nil` 窄化后字段与方法访问、enum tag/variant/比较、整数/字符串/bool/enum `match` 表达式、block 表达式、算术/比较、`let`、重赋值、函数、显式 `return` 与尾表达式返回、`if`、条件 `for`、range `for i in start..end`、`break`、`fs.read_file`/`fs.write_file`、`map[K,V]` 的构造/读写/`map_has`/`len(map)`、函数调用与 `io.println`。
- LLVM 后端链接 `runtime/ncrt.h` + `runtime/ncrt.c` 编译出的 `ncrt.obj`。`ncrt` 固定基础 ABI：`str`、`nc_map`、`nc_slice_raw`、`__nc_gc_alloc`/`__nc_gc_collect`/`__nc_gc_live`、root slot、字符串/file/cast/map helper、字节级 slice append/copy helper 与 C 异常入口。除 `runtime.gc_collect()` / `runtime.gc_live()` 外，其他 `ncrt` helper 都是编译器私有 ABI。`[]T` 语言布局仍为 `{ T* ptr; u64 len; u64 cap }`，`elem_size` 仅作为 runtime helper 调用参数传入，不进入 slice header。
- LLVM `map[K,V]` 当前运行时布局匹配 `ncrt.h` 的私有 `nc_map`：`{ entries, cap, len, tombstones }`，entries 在 LLVM 侧为 opaque pointer；get/set/has 统一调用 `ncrt` tagged scalar 哈希表实现，`len(map)` 读取 len 字段。
- LLVM slice、map、closure env、heap struct 与运行时构造字符串的动态存储统一通过外部 `__nc_gc_alloc` 分配；该入口由 `ncrt.obj` 提供。共享 `ncrt` 当前实现显式 mark-sweep GC：`gc_collect()` 从已注册 root slot 出发标记可达块，保守扫描已标记 heap payload 内的 machine word，释放不可达块；`gc_live()` 返回当前存活 GC block 数。
- LLVM 后端负责为持有 GC 指针的栈槽注册 root：`str.ptr`、`[]T.ptr`、`nc_map.entries`、`*T/?*T`、function value `env`、struct 字段和定长数组元素。LLVM 函数/closure 会为参数、receiver、closure env、局部变量、返回槽、catch/throw 值注册 root，并在所有出口 rewind 到函数入口 mark。
- LLVM `throw`/`try`/`catch` 当前使用轻量异常模型：全局异常 flag + `str` value，函数边界返回默认值传播异常，`try` 块在语句边界检查 flag 并跳转 `catch`；uncaught throw 在 `main` 输出到 stderr 并返回 1。`defer` 使用函数内动态 site 栈，按 LIFO 在函数 fallthrough、显式 `return`、`throw` 传播前执行。该模型不依赖 `setjmp`/`longjmp`。
- LLVM function value 当前支持 `{ call, env }` 胖指针：`call` 首参为 `i8* env`，无捕获时 `env == null`；捕获 closure 生成 env struct 并按值拷贝捕获字段，env 通过 `__nc_gc_alloc` 分配并由 function value 的 `env` root 与保守 heap 扫描保活。
- LLVM 接口值当前支持 `{ vtable, data }` 胖指针，LLVM 表示为 `{ i8*, i8* }`。每个实际使用的 `*T -> I` 转换生成接口专属 vtable 全局常量与 erased receiver thunk；接口方法调用从 vtable 取函数指针并以 `data` 作为 receiver 动态分派。GC root 只登记接口值的 `data` 字段，`vtable` 是全局常量。
- LLVM 后端当前使用 MinGW GNU triple `x86_64-w64-windows-gnu` 生成 Windows COFF object，并用 `gcc` 链接。
- LLVM 后端是语言全集和回归权威；不向前兼容未声明支持的节点，遇到未支持语义应明确报错。

LLVM 默认后端达标门槛：

- LLVM 后端通过全部 `test_cases` 正向/错误用例，以及项目级 import/module 测试。
- str、slice、array、struct、enum、match、nullable pointer、closure/function value、defer/throw/try/catch、动态分配保活、runtime helper 链接路径均有 LLVM 覆盖。
- 类型标注在 public AST/pass 边界暂仍保存为字符串，但内部解析/格式化集中走 `TypeRef` 工具层；type alias `type Name = Type` 在前端展开为底层类型字符串，对后续所有 pass（泛型实例化、typecheck、LLVM codegen）透明。
- `python nc.py compile <target>`、`python nc.py build <target>` 走 LLVM；不再提供 C 后端回归入口。
- LLVM 默认后端已接入共享 `ncrt` 显式 GC；当前 GC 不后台运行，也不在分配时自动触发，只有显式 `gc_collect()` 会回收不可达对象。
- 若迁移中确认其他能力暂时放弃或延期，必须在 worklog/design 中记录放弃点、原因和替代边界。

---

## 三、可见性

**默认公开，`_` 前缀即私有。**

```nc
fun serve(port: i32) { ... }         # 公开 —— 外部 import 后可见
fun _helper(x: i32): i32 { ... }     # 私有 —— 仅模块内可见
```

关键字：**`fun`**（非 `fn`）。

后端符号生成时：
- 公开 → 可被导入模块通过命名空间限定访问
- 私有（`_` 前缀）→ 仅模块内可见，跨模块访问报错

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
| `str` | builtin scalar/runtime value type，LLVM/ncrt 布局为 `{ u8* ptr; u64 len }` |
| `[]T` | `{ T* ptr; u64 len; u64 cap }` |
| `map[K,V]` | 编译器私有 `nc_map`，布局为 `{ entries; i64 cap; i64 len; i64 tombstones }` |
| `[N]T` | 内联在 struct/栈中，如 C 数组 |
| `*T` | 单个指针，非空 |
| `?*T` | 单个指针，C 布局同 `*T`，可为 `nil` |
| 接口值 | `{ type* vtable; void* data }` 胖指针 |

切片语义：

- `a[lo:hi]` 总是复制元素，生成新的底层存储；适用于 `str`、`[]T`、`[N]T`。
- 切片结果与原值不共享可变底层数组；对结果做索引赋值或 `append` 不会写回原数组/原切片。
- `[]T.cap` 是当前底层存储容量；切片复制结果的 `cap == len`。

map 语义：

- `map[K,V]` 是内建泛型 map 类型，构造语法为 `map[K,V]()`。
- v1 只支持标量 key/value：`i8/i16/i32/i64/u8/u16/u32/u64/f32/f64/bool/rune/str`。非标量 key 或 value 不支持。
- `m[k]` 要求 `k: K`，返回 `V`；缺失 key 返回 `V` 的零值。
- `m[k] = v` 要求 `v: V`；`m[k] += v` 等复合赋值按 `V` 类型复用对应运算符规则。
- `map_has(m, k)` 要求 `m: map[K,V]` 且 `k: K`，返回 `i32`。
- `len(m)` 返回 map 当前条目数，类型为 `i32`。
- `map_new()`、裸 `nc_map` 和旧字符串专用 map helper 不是语言边界，不保留向前兼容。

`size_of(T)` 是语言级编译期内建表达式，只接受类型实参，不调用用户函数，返回类型为 `u64`。它返回当前 LLVM/ncrt ABI 下类型 `T` 的运行时布局大小：基础标量按实际宽度，`str` 为 16，`[]T` 为 24，`map[K,V]` 为 32，函数值与接口值为 16，指针与 nullable pointer 为 8，enum/rune 为 4，数组按元素 ABI stride 乘长度，struct 按字段偏移、padding 和最终对齐计算。`size_of(void)` 非法；命名/限定类型必须存在且遵守跨模块 `_` 私有可见性；嵌套类型组件会递归校验。

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
| `'A'` | `rune` | — |

字符字面量表示单个 Unicode 码点，类型为 `rune`。支持普通字符与转义：`'\n'`、`'\t'`、`'\r'`、`'\''`、`'\\'`、`'\u{4E2D}'`。空字符字面量、多码点字符字面量、非法或越界 Unicode 码点在编译期报错。

### 4.5 类型转换

采用 **函数式** 语法：`目标类型(值)`。

```nc
let x: i64 = i64(42)
let y: u8 = u8(255)
let z: f32 = f32(3.14)
let r: rune = rune(65)
let n: i32 = i32(r)
```

`rune(i32)` / `rune(u32)` 是整数到码点的显式转换；`i32(rune)` / `u32(rune)` 是码点到整数的显式转换。`str(rune)` 返回该码点的 UTF-8 字符串。`rune` 底层 LLVM 宽度为 `i32`，零值为 `0`，但类型系统不把它当普通 numeric：不参与算术、大小比较、位运算、复合赋值或自增自减，只允许同类型 `==` / `!=`。

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

### 4.8 显式泛型 v1

泛型当前只支持函数和 struct，使用显式类型实参，并在前端 monomorphization 为普通声明后再进入符号表、类型检查和后端。

```nc
fun id[T](x: T): T { x }
fun pick[T any](x: T): T { x }

struct Box[T] { value: T }

fun main() {
    let a = id[i32](42)
    let b = Box[str] { value: "ok" }
    let c = new Box[i32] { value: 7 }
}
```

当前边界：

- `[T]` 与 `[T any]` 等价；v1 只有 `any` 约束。
- 调用泛型函数必须显式写类型实参：`id[i32](x)`；不做类型实参推断。
- 使用泛型类型必须显式写类型实参：`Box[i32]`、`[]Box[str]`、`*Box[i32]`、`Box[Box[i32]]`。
- 未实例化的泛型模板不进入后端，不生成代码；每个使用到的实例生成稳定普通名，如 `id__i32`、`Box__str`。
- 泛型函数体按具体实例检查；类型不匹配在实例化后的普通函数/struct 上报错。
- 泛型方法（receiver 自带类型参数）暂不支持；可为具体实例类型写普通方法，例如 `fun (b *Box[i32]) get(): i32`。
- 不支持 `comparable`、`numeric`、接口约束、类型集合、运行时类型擦除或胖指针泛型。

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
let f: fun(i32) i32 = twice
```

函数值类型标注使用 `fun(params) Ret`，例如 `fun(i32) i32`、`fun() str`、`fun(i32, str) bool`。旧 `(i32) -> i32` 函数类型语法不保留。

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
fun (f *File) write(data: []u8): i32 { ... }
```

接口 v1 边界：

- `iface Name { ... }` 只能出现在顶层，进入全局类型命名空间，参与 import 模块名前缀改写和 `_` 私有规则。
- 接口方法项只允许签名，不允许函数体；嵌入项只允许接口名。嵌入会扁平化为 method set，并检测未知嵌入、循环嵌入和同名方法签名冲突。
- struct 自动满足接口，不写 `implements`。v1 只采纳现有指针 receiver 方法：`fun (p *T) method(...)`。值 receiver、`T` 值类型、`?*T`、slice、函数值等都不会隐式装箱为接口。
- 接口值支持作为局部变量、函数参数和函数返回值；接口方法调用按接口 method set 校验参数和返回类型，并通过 vtable 动态分派。
- v1 不支持接口到接口隐式转换或重装箱；`ReadWriter` 值不会自动降为 `Reader`。若源表达式本身是 concrete `*T`，可在目标接口处重新装箱。
- v1 不支持泛型接口、接口约束、显式 implements、类型断言、接口 nil 零值或从接口取回 concrete 类型。

---

## 十、错误处理

**throw 不标注类型。defer 清理（LIFO）。**

```nc
fun load_config(path: str): str {
    if path == "" { throw "empty path" }
    return contents
}

fun process(path: str) {
    let f = open(path)
    defer { f.close() }
    # 无论正常返回还是 throw，defer 都会执行
}

try {
    let data = fs.read_file("config.nc")
} catch e {
    io.println("error: {e}")
}
```

---

## 十一、元编程

**v1 不引入通用 `comptime`。**

当前决策：

- 不提供 `comptime fun`。
- 不提供 `comptime if`。
- 不提供编译期执行用户代码的解释器或求值环境。

理由：

- NC 没有 C 头文件模型，模块系统已经替代 `#include` / include guard。
- `let` 的编译期常量形态覆盖简单 `#define` 常量。
- 显式泛型 v1 已覆盖类型级复用和单态化生成代码的主要需求。
- 当前 LLVM-only 目标下，还没有真实 case 证明需要平台级条件编译。
- 通用 `comptime` 会引入编译期执行、副作用、错误定位、缓存、类型生成和 pass 边界等复杂问题，不符合当前 case 驱动原则。

后续只在具体 case 推动下考虑窄化能力，例如：

- 常量表达式求值。
- `static_assert(expr)`，且只接受编译期常量表达式。
- `cfg` / build config，用于平台或 feature 分支。
- 其他有限内建常量表达式。

---

## 十二、FFI

```nc
extern {
    fun putchar(c: i32): i32
    fun strlen(p: *u8): u64
}

extern "msvcrt.lib" {
    fun _sopen(path: *u8, oflag: i32, pmode: i32): i32
}
```

extern v1 只支持纯声明，不允许函数体。关键字 `extern` 后可跟一个可选的 lib 或 dll 路径字符串（如 `"msvcrt.lib"`、`"kernel32.lib"`、`"user32.dll"`），构建系统会在链接时追加该文件作为输入。不含路径时，符号由链接器从默认路径解析。

省略返回类型表示 `void`。允许类型限于 C ABI scalar/pointer：`i8/i16/i32/i64/u8/u16/u32/u64/f32/f64/bool/*T/?*T/void`。不支持 varargs、回调、头文件解析、extern struct、泛型 extern、`str`/slice/map/array/struct/enum/function value、聚合类型按值传递。

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
| 字符串插值 | `"Hello, {expr}"` |
| 数值溢出 | 静默截断（wrapping，如 C） |
| 空指针 | `*T` 非空；`?*T` 可为 `nil`；nullable deref 由类型系统禁止 |
| 指针类型 | `*T` / `?*T`，不设 `*const T` |
| 方法定义 | 任意模块可扩展，不可重名 |
| 顶层变量 | 禁止跨模块使用 |
| `if` 表达式 | 全部 `if` 都是表达式；无 `else` 时类型为 `void`；有 `else` 时分支类型一致 |
| 条件循环 | 使用 `for condition { ... }`，无 `while` 关键字 |
| block 表达式 | `{ statements; tail_expr }`，值来自尾表达式 |

字符串插值 v1：

- 插值段支持任意表达式：`"x={a + 1}"`、`"name={user.name}"`、`"v={f(1)}"`。
- 编译期降为字符串拼接；非 `str` 插值表达式必须有 `str(...)` 转换规则，目前支持 `str`、`rune`、`bool`、整数和浮点。
- 字符串里的字面量 `{` / `}` 写作 `{{` / `}}`。
- 未闭合 `{`、空 `{}`、单个未转义 `}` 报编译错误。
- `str[index]` 当前仍保持字节索引语义，返回 `i32`，本轮不改为 rune/codepoint 索引。
