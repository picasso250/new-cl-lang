# NC (New C) — 语言设计

> 本文件只记录"我们要什么"和 why。标准库 API 见 `docs/stdlib.md`；泛型约束族细节见 `docs/generics.md`；内部 ABI 与构建规范见 `docs/internal-abi.md`；并发模型设计见 `docs/concurrency.md`；实现过程见 `worklog.md`。

## 目标

NC 是"更好的 C"：

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

我们要"目录即模块"：

- 模块名由目录名推断。
- 同目录 `.nc` 文件共享命名空间，自动互见。
- 跨模块必须显式 `import`。
- 导入后必须用模块名限定访问：`foo.add()`、`foo.User`。
- `_` 前缀顶层符号是模块私有。
- 标准库模块名由编译器保留，优先于同级用户目录。

当前边界：import v1 只支持一级模块名；不支持包路径、别名导入、选择性导入或单文件模块。

why：目录模块比单文件模块更适合真实工程组织；限定访问能避免隐式名字污染；`_` 私有规则简单，不引入 `pub/private` 额外关键字。

## 可见性

默认公开，`_` 前缀私有。

why：小项目里默认公开更少仪式感；私有命名规则足够直观，也符合当前不增加关键字的取向。

## 类型

我们要一组明确、低魔法的基础类型：

```nc
i8 i16 i32 i64
u8 u16 u32 u64
f32 f64
bool str rune void
*T ?*T
[]T [N]T
map[K,V]
fun(T) R
```

核心语义：

- `str` 不可变，表示 UTF-8 字节串。
- `rune` 表示 Unicode 码点，不当作普通 numeric 使用。
- `*T` 非空；`?*T` 可为 `nil`。
- `[]T` 是动态切片；`[N]T` 是定长数组。
- `map[K,V]` 是语言内建泛型 map。key 必须是非 float 的可哈希比较类型；value 必须是有零值的 sized 类型。
- 函数值类型写作 `fun(params) Ret`。
- 非空 slice literal 可写作 `[]{...}` 并从首元素推导元素类型；空 slice literal 仍必须写 `[]T{}`。
- 非空 map literal 可写作 `map{key: value, ...}` 并从首个 key/value 推导 key/value 类型；空 map literal 仍必须写 `map[K,V]{}`。

简单推断原则：类型可在声明本体内简单推出时，可省略类型声明。
- 表达式自足推断只使用当前声明自带的 initializer、默认值或 literal，不从赋值目标、调用点、泛型实参或后续使用反推。
- 函数返回类型可由函数体内部非递归返回路径或尾表达式推导；递归函数仍必须显式返回类型。
- 无后缀字面量默认类型为：整数 `i32`、浮点 `f64`、字符串 `str`、bool `bool`。
- 非空 slice/map literal 从首个元素或首个 key/value 推导具体类型；后续元素或 entry 必须同类型，不做隐式数值提升或共同类型搜索。
- struct literal 仍必须写具体类型名；不通过目标类型反推，也不引入匿名 struct。

why：指针非空默认能避免 C 式空指针常态化；nullable pointer 显式表达风险；`rune` 独立于 numeric，避免字符和整数混用；函数类型使用 `fun` 语法，和函数声明保持一致；简单推断只消除重复标注，不引入跨位置推断。

## 零值

我们要 Go 式零值：数值为 `0`，bool 为 `false`，str 为 `""`，nullable pointer 为 `nil`，slice 为 nil/空切片，struct 字段递归零值。非空 `*T` 没有零值，声明时必须初始化。

why：零值让局部初始化和容器默认值更简单；非空指针没有零值，让类型系统维护它的承诺。

## 转换

我们要显式转换：`let x = i64(42)`、`let s = str(123)`。

- 数值类型之间不做隐式提升。
- 跨数值类型必须显式转换。
- `str(...)` 只支持语言定义的可字符串化类型。
- `size_of(T)` 是语言级编译期内建，返回当前 ABI 下的布局大小。

why：C 的隐式提升容易制造隐藏 bug；显式转换让代码生成和错误定位更直接；`size_of(T)` 是系统语言刚需，但不需要通用 comptime。

## 变量

变量用 `let` 声明，声明后可重赋值。

```nc
let x: i32 = 5
x = 6
x += 1
```

复合赋值 `+= -= *= /= %= &= |= ^= <<= >>=` 是语句，复用对应二元运算符的类型规则。

名字为全大写形式的 `let` 绑定不可重赋值（仅 ASCII `A-Z`、`0-9`、`_`，至少含一个字母）。不可重赋值不是编译期常量；初始化表达式可为普通运行期表达式。不引入深度不可变。

我们不要 `const` / `mut` 作为 v1 语言边界。

why：全大写不可重赋值规则解决最小常量需求，不提前设计不可变性系统。

## 函数

我们要：

- 关键字使用 `fun`。
- 单返回值。
- 支持显式 `ret` 和尾表达式返回。
- 支持闭包和函数值。
- 普通函数名可作为无捕获函数值使用；泛型函数必须完全实例化后才能作为函数值。

```nc
fun add(x: i32, y: i32): i32 { x + y }
let f: fun(i32) i32 = fun(x: i32): i32 { x * 2 }
fun clamp(x: i32, lo: i32 = 0, hi: i32 = 100): i32 { ... }
```

默认参数规则：

- 参数可写类型 `name: T = expr`；也可在默认值能推出类型时写作 `name = expr`。无默认值参数仍必须显式写类型。
- 默认参数必须位于非默认参数之后；调用时只能省略尾部默认参数。
- 省略的实参在调用端用声明处默认表达式补齐，每次省略重新求值（不共享可变默认值）。
- 默认值使用无调用的值构造表达式（literal、前序参数引用、struct/slice/map literal、函数值、显式类型转换）；不可包含普通函数调用、方法调用或可错操作（`??`、`!!`、`try`）。
- 泛型函数默认参数表达式只在调用省略该参数时实例化；显式传参时默认表达式不参与该调用。
- 默认值表达式按声明处上下文检查，只能引用前面已声明参数和可见全局符号。
- 默认参数不改变函数 ABI、函数值类型或闭包调用 ABI；extern、iface 方法和函数类型不支持默认参数。

why：单返回值降低调用、类型检查和 ABI 复杂度；闭包是现代工程语言的基本能力，但性能目标允许胖指针和间接调用。

## 控制流

我们要表达式化控制流：

- `if` 是表达式。
- `match` 是表达式。
- `match error` 使用字符串字面量按错误 message 完整匹配，并且必须有 `else`。
- `ret`、`err` 等不回汇合点的分支在内部视为 `never`，可与其他分支值类型合并；`never` 不作为用户可写类型暴露。
- 条件循环写作 `for condition { ... }`。
- slice 遍历写作 `for i, item in items`，`i` 为 `i32`。
- map 遍历写作 `for key, value in m`。
- 使用 `break` 跳出循环。

我们不要 `while`、`switch` 关键字。

why：控制流少而统一，语法面更小；`match` 比 `switch` 更适合后续扩展到 enum、字面量和模式。

## 自定义类型

我们要 `struct`、`enum`、`iface`、`type Name = Type` 类型别名、显式泛型 v1（用于函数和 struct）、Go 式 struct 嵌入。

struct 嵌入规则：

- 嵌入字段是真实字段，字段名为嵌入类型短名。必须用字段名显式初始化：`B { A: A { ... }, y: 1 }`。
- `b.A`、`b.A.x` 和 `b.A.foo()` 可用；嵌入字段和方法在无冲突时提升为 `b.x` 和 `b.foo()`。
- 提升冲突在 struct 声明期报错，不做覆盖或顺序选择。
- 嵌入是组合，不是子类型；`B` 不可隐式当作 `A` 使用。
- 递归 struct 只允许经由固定大小引用形状打断布局；直接值递归应明确报错。

接口规则：

- struct 自动满足接口，不写 `implements`。
- v1 只采纳指针 receiver 方法。
- 接口值是胖指针。

泛型规则（详见 `docs/generics.md`）：

- 必须显式写类型实参。
- v1 支持 `any` 和标准库约束 `types.Eq`、`types.Ord`、`types.Hash`、`types.Zero`。
- `types.Ord` 支持数值类型、`str` 和具备合法 `__lt__` 的 struct。
- 已完全实例化的泛型函数可作为函数值使用。
- 递归函数需要显式返回类型，避免返回类型推导成环。

why：struct/enum 覆盖系统建模的基本需要；接口采用结构化满足减少声明耦合；显式泛型避免 v1 引入类型推断。

## 方法

方法可定义在 struct 上，使用指针 receiver：

```nc
fun (p *Point) move(dx: f64, dy: f64) { ... }
```

我们允许扩展方法，但不允许同名覆盖。方法调用是 receiver 函数 ABI 的语法糖。

why：方法扩展有利于模块组织；禁止覆盖可保持调用解析简单、稳定。

## 运算符

我们要 C/Go 风格基础运算符，但不继承 C 的隐式数值提升。

核心规则：

- 算术、取模、大小比较要求两侧数值类型一致。
- `%` 和位运算 `& | ^ ~ << >>` 只支持整数；二元位运算要求两侧类型一致。
- 复合赋值 `+= -= *= /= %= &= |= ^= <<= >>=` 复用对应二元运算符规则。
- 指针不参与算术、索引或大小比较。同类型指针只允许 `==` / `!=`。
- 同类型 struct 允许 `==` / `!=`，按字段递归比较；字段类型也必须可比较。
- slice、数组、map、函数值和接口值不参与 `==` / `!=`。
- float 类型不允许作为 map key。
- 自增/自减是语句，不是表达式。

struct 可通过窄版特殊方法重载运算符：

- `+ - * / %` 对应 `__add__ __sub__ __mul__ __div__ __mod__`，返回同类型。
- 一元 `-` 对应 `__neg__`，返回同类型。
- `< <= > >=` 对应 `__lt__ __le__ __gt__ __ge__`，返回 `bool`。`__lt__` 是 `types.Ord` 的 struct 核心能力。
- 缺少手写 `__le__`/`__gt__`/`__ge__` 时，分别由 `__lt__` 派生为 `!(b < a)`/`b < a`/`!(a < b)`。
- 二元特殊方法必须是 `fun (x *T) __op__(other: T): T/bool`；一元 `__neg__` 必须是 `fun (x *T) __neg__(): T`。
- 不支持 `__eq__`、`__ne__`、反向运算、异构运算或自定义返回类型。

why：保留熟悉语法；删除 C 中最容易隐藏错误的隐式转换和指针算术；`==` / `!=` 保持结构相等，避免破坏 map key、`types.Eq` 和 hash 一致性。

## 错误处理

我们要 Go 风格的显式错误返回，但不采用源码双返回：

```nc
fun load(path: str): str err {
    if path == "" { err "empty path" }
    ret fs.read_file(path)??
}

fun main() {
    let text = load("config.nc") err? e {
        io.println("load failed")
        "default"
    }
    io.println(text)
}
```

核心规则：

- `error` 是 opaque 内建错误对象，不等同于 `str`，不参与比较或 map key 哈希。v1 允许 `str` 在 `err` 位置隐式构造为 `error`。
- `err expr` 立即结束当前函数，执行已登记 defer，并把错误返回给调用者。
- 函数是否可错由函数体推导；可在返回类型后写 `err` 作为显式可错断言。写了 `err` 标注但函数体不会把错误返回给调用者时，应报错。
- 函数值类型可写 `fun(T) R err`；v1 不支持可错函数值 ABI。
- 可错调用必须带后缀处理：`??`（传播）、`!!`（打印栈并退出）、`err? e { ... }`（fallback）、`match? e { ... }`（按 message 分类）或 `try` 语句。
- `try value = call() { ... } else e { ... }` 是语句，成功值只在成功块内可见，错误对象只在错误块内可见。省略 `else` 时失败行为等同于 `!!`。
- `else e` 中可用 `match e { "message" -> expr; else -> expr }` 按 message 完整字符串分类；pattern 只接受字符串字面量。
- `defer` 按 LIFO 执行；`ret`、`err` 和函数正常退出都必须执行已登记 defer。`defer` 中禁止 `err` 和 `??`。

当前边界：可错 callable 只覆盖普通函数和 struct 方法；extern、iface 方法、函数值和闭包不支持可错。`!!` 和 main 未捕获错误打印 `error: message` + `stack:` 与 frame 列表。不开放 message 读取、wrap、code/tag 或自定义错误类型。不提供 `throw`、`try/catch`、panic 或 recover。

why：错误路径必须在调用点显式可见；`defer` 解决资源清理路径分裂问题但不承担错误捕获职责；不引入栈搜索异常。

## 内存管理

我们要 GC：用户不手动释放普通 NC 对象。运行时提供 `runtime.gc_collect()` 与 `runtime.gc_live()`。当前不承诺后台 GC 或分配时自动触发。

why：目标是减少 C 的生命周期负担；项目仍在 case 驱动阶段，先保守落地显式 GC，再由真实压力推动自动触发策略。

## 标准库

我们要显式 import 的标准库模块。标准库能力不应伪装成裸语言魔法。当前标准库边界见 `docs/stdlib.md`。

why：显式 import 能让依赖和命名空间清楚。

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

- extern 只声明外部符号；可选字符串表示链接输入；允许声明级链接符号别名。
- v1 只支持 C ABI scalar/pointer。聚合类型按值传递不进入当前边界。

why：系统语言必须能调用 C；聚合 ABI 在不同 target 上差异大，不能用"看起来能跑"的 lowering 代替真正 ABI 分类。

## 元编程

v1 不引入通用 `comptime`。当前只接受具体、窄化的编译期能力：

- `size_of(T)`。
- 源码位置魔术常量：`__FILE__ : str`（与错误栈一致的相对路径，无路径时 fallback `<memory>`）、`__LINE__ : i32` 和 `__COL__ : i32`（1-based 位置）、`__FUNC__ : str`（函数显示名：普通函数 `foo`，方法 `Type.method`，闭包 `lambda N`）、`__MODULE__ : str`（目录模块名，无路径时 fallback `<memory>`）。魔术常量是编译器提供的只读表达式，不可声明同名符号，也不可作为赋值目标。
- 后续可能的常量表达式、`static_assert`、`cfg` / build config。

why：通用 comptime 会引入编译期执行、副作用、缓存、错误定位和类型生成复杂度；当前还没有 case 证明需要完整 comptime。

## 注释

只支持行注释：`# comment`。

why：语法简单；不处理块注释嵌套和词法边界问题。

## 逗号列表

`()`、`[]` 和 `{}` 包围的逗号分隔列表允许尾逗号。非包围语法逗号不属于该规则（如 `for i, item in items`）。

why：多行编辑和生成代码更稳定；规则限定在包围列表内，避免扩散到控制流语法。

## 构建与目标

我们要自带构建系统：

- `compile` 输出 LLVM IR；`build` 输出可执行文件及运行时对象。
- 支持显式 target：`windows-x64`、`linux-x64`。
- `build` / `run` 生成 hosted 用户态程序，始终通过目标平台 C runtime 和默认启动环境链接。v1 不提供 freestanding / `nostd` 模式。
- 内部 ABI 与模块对象缓存规则见 `docs/internal-abi.md`。

why：NC 不应依赖用户手写 make/cmake 才能完成基本构建；target 必须显式进入编译模型，FFI 和标准库都依赖它；GC、启动参数、stderr/error 退出、字符串/容器 runtime 以及标准库能力都依赖普通用户态 C runtime。

---

## 并发模型（M:N 绿色线程）

我们要 Go 风格的 N:M 绿色线程（green thread），由 `go f()` 关键字启动。

- `go` 是语句，只接函数调用（含闭包），不产生值。
- `main` 本身也是一个 green thread（live_count 初始为 1），进程在 main 结束且所有用户 green thread 退出后才 exit。
- 调度器实现为 ncrt C runtime：M 个 OS worker（M = NumCPU）从全局 run queue 取 green thread 执行。
- 每个 green thread 固定 64KB 栈 + guard page；上下文切换用汇编 save/restore callee-saved registers + %rsp（按 SysV / Win64 ABI 分开实现）。
- G 状态机：G_RUNNABLE / G_RUNNING / G_WAIT_MUTEX / G_WAIT_TIMER / G_DEAD。
- 合作式 yield：编译器在函数入口、loop backedge、alloc 点插入时间片 / safepoint 检查。
- 同步用标准库 `sync.Mutex`（handoff ownership，internal spinlock 保护 state + wait queue）。
- 阻塞模拟用 `sleep`（timer 优先队列，调度器每轮检查过期 timer）。
- GC STW 通过完全合作式 safepoint 实现（函数入口 + loop backedge + alloc 点），v1 不做信号/APC 异步抢占。
- 死锁检测：所有 live G 都阻塞且无待触发 timer 时，检测为 deadlock panic。
- v1 不做 channel/select、TCP netpoller、工作窃取、动态栈增长。

why：并发是现代系统语言的核心能力；Go 的 goroutine 模型经过工业验证；case 驱动最小 v1 先覆盖 go + mutex + sleep + 死锁检测 + 合作式 GC，后续由真实需求推动 I/O 和 channel。

详细设计见 `docs/concurrency.md`。

---

> 本文件只记录"我们要什么"和 why。实现细节、CLI 参数参见 README 和专题文档。
