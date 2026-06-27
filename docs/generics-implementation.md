# 泛型实现：类型擦除 + 描述符传递

> 本文记录泛型函数的内部实现方案。用户语义边界见 `docs/generics.md`。
>
> 当前实现：AST 级单态化（`compiler/generics.py` → `monomorphize()`），每个具体类型生成完整函数副本。
> 目标实现：类型擦除 + 编译器推导描述符，泛型函数在定义模块只编译一次。

## 动机

当前 C++ 风格的单态化存在结构性风险：

- **二进制膨胀**：sort 模块 8 个泛型 helper，每种类型生成 9 个 LLVM 函数。实测每个类型增加 ~5KB EXE / ~51KB IR。
- **模块重复编译**（未来）：`--keep-objs` 路径下，调用端每用一个新的 `sort.sort[NewType]`，sort 模块的 IR 指纹变化，sort 模块需要重新编译并走 O2 优化。
- **编译时间不可控**：和 C++ templates 同一病因——定义模块的编译成本随调用端类型数量线性增长。

Go 1.18+ 通过 GC Shape + 字典传递避开了这个病根，编译速度保持快。本方案吸收 Go 的设计，NC 化落地。

## 范围

| 项目 | 变更 |
|------|------|
| 泛型函数 | **擦除**：定义模块只产出描述符驱动的版本，调用端传描述符 + thunk |
| `monomorphize` 关键字 | **先不加**，等有 case 证明需要热路径逃逸再说 |
| 泛型 struct（`struct Box[T]`） | **不动**，保留当前单态化；泛型 struct 当前零用例 |
| 泛型函数值（`id[i32]`） | **擦除**：调用端生成一个包装 thunk，绑定描述符 |
| 约束族（Eq/Ord/Hash/Zero） | **保持**，typecheck 期校验不变，但操作改为走描述符 |
| 非泛型函数 | **完全不动** |

## 架构总览

```
                  ┌─────────────────────┐
                  │   定义模块（sort）    │
                  │                     │
                  │ fun sort[T](xs,less)│
                  │    ↓ 编译器分析     │
                  │ 需要: lt, size      │
                  │    ↓ 生成描述符类型 │
                  │ struct SortDesc {   │
                  │   size: i32,        │
                  │   lt: fn(*D,raw,raw)│
                  │ }                   │
                  │    ↓ AST 改写       │
                  │ fun sort(           │
                  │   desc: *SortDesc,  │
                  │   xs: []raw,        │
                  │   less: fn(*D,raw,raw)│
                  │ )                   │
                  │    ↓ 编译一次 ✅    │
                  │   sort.o (不变)     │
                  └─────────┬───────────┘
                            │ 隐式依赖 SortDesc 布局
                            ↓
                  ┌─────────────────────┐
                  │  调用模块（main）    │
                  │                     │
                  │ sort.sort[i32](xs)  │
                  │    ↓ 编译器生成     │
                  │ let i32_desc =      │
                  │   SortDesc {        │
                  │     size: 4,        │
                  │     lt: builtin_lt  │
                  │   }                 │
                  │    ↓ 调用改写为     │
                  │ sort(&i32_desc,     │
                  │      xs_as_raw,     │
                  │      less_default)  │
                  └─────────────────────┘
```

## 擦除后值 ABI（erased value ABI）

类型擦除后，具体类型 T 的值不再能嵌入 LLVM 寄存器或栈槽——编译器不知道它多大。所有 T 值统一走 **caller-provided slot**：

- `raw` 是编译器内部 TypeRef，表示 **指向 desc.size 字节内存的指针**（LLVM 层 lowering 为 `i8*`）。用户源码不可写 `raw`。
- 调用端在调用前分配 slot（alloca desc.size 字节），传 slot 地址给 callee。
- callee 通过 slot 指针读写 T 值，不负责分配/释放。
- 返回值也走 out-param：调用端分配 ret slot，callee 写入。

### 例子：id[T]

```
// 用户源码
fun id[T](x: T): T { x }

// 擦除后 ABI（编译器内部，伪代码）
fun id(desc: *IdDesc, ret: raw, x: raw) {
    // ret 和 x 都是 i8*，各指向 desc.size 字节
    memcpy(ret, x, desc.size)
}

// 调用端 id[i32](42)
let x_slot = alloca i32; store i32 42, i32* x_slot
let ret_slot = alloca i32
id(&i32_desc, bitcast ret_slot, bitcast x_slot)
let result = load i32, i32* ret_slot
```

### 例子：_sort_swap

```
// 用户源码
fun _sort_swap[T](items: []T, a: i32, b: i32): void {
    if a == b { ret }
    let tmp = items[a]
    items[a] = items[b]
    items[b] = tmp
}

// 擦除后 ABI（编译器内部，伪代码）
fun _sort_swap(desc: *SortDesc, items: []raw, a: i32, b: i32) {
    if a == b { ret }
    // tmp 在 callee 栈上分配
    let tmp_slot = alloca desc.size bytes
    // items[a] → &items_data[a * desc.size]
    memcpy(tmp_slot, &items_data[a * desc.size], desc.size)
    memcpy(&items_data[a * desc.size], &items_data[b * desc.size], desc.size)
    memcpy(&items_data[b * desc.size], tmp_slot, desc.size)
}
```

### slot 生命周期规则

| 场景 | slot 提供者 | 生命周期 |
|------|------------|---------|
| T 类型参数（传入） | 调用端 | 调用期间 |
| T 类型返回值 | 调用端（out-param） | 调用端自行管理 |
| `let tmp: T`（局部变量） | callee（alloca desc.size） | 当前函数帧 |
| `items[a]` 作为右值（取地址） | 指向 slice 数据的指针 | 和 slice 一致 |

## 描述符推导

编译器从泛型函数体（及其调用的子函数）收集对类型参数 `T` 的所有操作。

收集依赖于类型信息——**必须先对泛型模板做 typecheck**（T 保持为类型参数），标注每个节点是否涉及 T，然后遍历标注后的 AST 收集操作。

### 注意：pass 顺序

操作收集不能放在 typecheck 之前。正确顺序：

```
parse → type_alias_expand → module_merge → symtab
    → template_typecheck   # typecheck 泛型模板（T 作为类型参数），标注 T-use
    → collect_desc_ops     # 基于标注后的 AST 收集操作
    → erase_generics       # AST 改写：签名 + 函数体
    → final_typecheck      # 按擦除后类型完整检查
    → llvm_codegen
```

`template_typecheck` 是现有 typecheck 的超集——在正常类型推断之外，额外记录每个表达式节点是否涉及类型参数 T（用于后续 op 收集）。

### 触发操作收集的 AST 节点

| AST 节点 | 收集的操作 | 描述符字段 |
|----------|-----------|-----------|
| `a < b` 其中 a,b 类型为 T | `lt` | `lt: fun(*Desc, raw, raw) bool` |
| `a > b` / `a <= b` / `a >= b`（从 `lt` 派生） | `lt` | 同上 |
| `a == b` / `a != b` 其中 a,b 为 T | `eq` | `eq: fun(*Desc, raw, raw) bool` |
| `let x: T = ...` | `size` | `size: i32` |
| `let x: T`（零值初始化，无 initializer） | `size` + `zero` | `zero: fun(raw)` |
| `x = y` 其中目标类型 T | `size` | 同上 |
| T 作为函数参数/返回值 | `size` | 同上 |
| `items[a]` 结果类型为 T | `size`（值拷贝） | 同上 |
| T 作为 slice 元素 `[]T` | `size` | 同上 |
| 对 T 调用 `hash()` | `hash` | `hash: fun(raw) u64` |

### 收集算法

```
collect_ops(func, T) → set of ops:
  ops = {}
  for each statement/expr in func.body (already type-annotated):
    if node is BinaryOp("<"|">"|"<="|">=") and operands typed T:
        ops.add(lt)
    if node is BinaryOp("=="|"!=") and operands typed T:
        ops.add(eq)
    if node is VariableDecl with type T and no initializer:
        ops.add(size); ops.add(zero)
    if node is VariableDecl with type T and has initializer:
        ops.add(size)
    if node is Assignment with target type T:
        ops.add(size)
    if node calls a function that is also generic and parameterized by T:
        ops.union(collect_ops(callee, T))
  return ops
```

### 描述符结构生成

收集完成后，编译器为泛型函数生成一个描述符 struct。注意描述符里的函数指针**统一签名带 `*Desc`**（比较器 ABI 一致，见下文）：

```
struct __desc_sort {
    size: i32,                              // sizeof(T)
    lt: fun(*SortDesc, raw, raw) bool,      // a < b（从 _sort_less_default 收集）
    // eq: 如果用了 == 才加
    // hash: 如果用了 hash() 才加
    // zero: 如果用了零值初始化才加
}
```

描述符 struct 在定义模块的 LLVM IR 里出现（`%__desc_sort = type { i32, i1 (i8*, i8*, i8*)*, ... }`），调用端生成对应的 LLVM 常量。

## AST 改写规则

### 泛型函数签名改写

类型擦除后的参数传递走 slot ABI。签名改写规则：

**改写前**（定义模块）：
```
fun sort[T types.Ord](items: []T, less: fun(T,T) bool = _sort_less_default[T]): void
```

**改写后**（定义模块，编译器内部）：
```
fun sort(desc: *SortDesc, items: []raw, less: fun(*SortDesc, raw, raw) bool): void
```

具体规则：
1. 去掉 `type_params`。
2. 在参数列表**最前面**插入隐式参数 `desc: *SortDesc`。
3. 所有类型为 `T` 的参数 → slot ABI：参数改为 `raw`（指向调用端分配的 slot）。
4. 返回类型为 `T` → out-param ABI：增加一个 `raw`（指向调用端分配的 ret slot）作为首个隐式参数（在 desc 之后）。返回类型改为 `void`。
5. `[]T` → `[]raw`（data pointer 为 `i8*`，len/cap 不变）。
6. `fun(T,T) bool` → `fun(*SortDesc, raw, raw) bool`。

### 比较器 ABI：统一带 desc

所有擦除后的 comparator 函数签名统一为 `fun(*SortDesc, raw, raw) bool`：

- `_sort_less_default(desc, a, b)` 调用 `desc.lt(desc, a, b)`
- 自定义 less thunk（见调用端章节）也接收 desc
- sort 内部所有调用 `less(desc, a, b)` 一致传 desc

### 泛型函数体改写

| 原 AST | 改写后 AST |
|--------|-----------|
| T 类型局部变量 `let x: T`（有 init） | callee alloca desc.size 字节，`x` 绑定为 raw（slot 地址），memcpy init 进 slot |
| T 类型零值初始化 `let x: T` (no init) | callee alloca desc.size 字节，调用 `desc.zero(x)` |
| `let x = expr`（推导为 T） | `x` 绑定为 raw（slot 地址），expr 结果 memcpy 进 x |
| `a < b`（a,b 类型为 T） | `desc.lt(a, b)` — a,b 已是 raw 指针 |
| `a == b` | `desc.eq(a, b)` |
| `items[a]`（items: `[]T` → `[]raw`） | 结果类型为 raw（元素 slot 地址：`&items_data[a * desc.size]`） |
| `let tmp = items[a]`（值拷贝） | `let tmp = alloca(desc.size); memcpy(tmp, &items[a], desc.size)` |
| `items[a] = tmp` | `memcpy(&items[a], tmp, desc.size)` |

### 用户语义收窄

类型擦除引入一项显式语义变更：

- **T 类型值不能直接传给非泛型函数**。例如泛型函数内调用 `helper(x: T)` 其中 `helper` 是接收具体类型的非泛型函数——不可行，因为调用端不知道 T 的具体类型。编译器应明确报错。
- 合法替代：通过 iface 方法调用（`x.some_method()` — iface 本来就走动态分派），或通过描述符操作。

### 默认参数改写

```
# 改写前
fun sort[T](..., less: fun(T,T) bool = _sort_less_default[T])

# 改写后：_sort_less_default 自身也被擦除
fun sort(desc: *SortDesc, ..., less: fun(*SortDesc, raw, raw) bool = _sort_less_default)
# _sort_less_default 签名：fun _sort_less_default(desc: *SortDesc, a: raw, b: raw): bool
```

调用端省略 `less` 时，编译器插入 `_sort_less_default` 作为实参（定义在 sort 模块，接收 desc），无需额外 thunk。

## 调用端：描述符生成

调用端看到 `sort.sort[i32](xs)`，需要生成：

### 1. 描述符常量

描述符常量标记为 `linkonce_odr` + `unnamed_addr`，由 linker 跨模块去重（COMDAT 语义）：

```
; 在调用端模块的 LLVM IR 里（linkonce_odr → linker 自动去重）
@__desc_sort_i32 = linkonce_odr unnamed_addr constant %__desc_sort {
    i32 4,                                           ; size
    i1 (i8*, i8*, i8*)* @__nc_builtin_lt_i32        ; lt
}, align 8
```

注意：不是 `private`（private 不能跨模块去重）。`linkonce_odr` 保证 N 个模块各自生成时 linker 只保留一份。

### 2. 调用端 slot 分配 + 调用改写

```
// 改写前：sort.sort[i32](xs)

// 改写后（编译器生成）：
let xs_raw = []raw { data: bitcast i32* → i8*, len: xs.len, cap: xs.cap }
// 无 T 类型显式参数，无需参数 slot；无返回值（void），无需 ret slot
sort.sort(&__desc_sort_i32, xs_raw, _sort_less_default)
```

如果泛型函数返回 T（如 `id[T](x: T): T`）：

```
// 改写前：let y = id[i32](42)

// 改写后：
let x_slot = alloca i32; store i32 42, i32* x_slot
let ret_slot = alloca i32
id(&__desc_id_i32, bitcast ret_slot, bitcast x_slot)
let y = load i32, i32* ret_slot
```

## 调用端：自定义 less 回调

用户写：
```
sort.sort[Point](pts, less = fun(a: Point, b: Point): bool { a.x < b.x })
```

编译器在调用端生成 thunk：

```
# 编译器生成的 thunk（在调用端模块）
fun __thunk_less_Point(desc: *SortDesc, a: raw, b: raw): bool {
    let pa: *Point = (*Point)(a)   # raw → Point 指针
    let pb: *Point = (*Point)(b)
    ret pa.x < pb.x
}
```

注意 thunk 签名是 `fun(*SortDesc, raw, raw) bool`——和 sort 里统一的 comparator ABI 一致。thunk 接收 desc，可以选择使用或忽略。这里 thunk 不需要 desc（`a.x` 是具体字段访问）但仍接受它以匹配 ABI。

## 调用端：泛型函数值

```
let f: fun(i32, i32) bool = less[i32]
```

擦除后，编译器在调用端生成 thunk：

```
# 编译器生成的 thunk
fun __thunk_less_i32(a_typed: i32, b_typed: i32): bool {
    let a_slot = alloca i32; store i32 a_typed, i32* a_slot
    let b_slot = alloca i32; store i32 b_typed, i32* b_slot
    ret less(&__desc_less_i32, bitcast a_slot, bitcast b_slot)
}
let f: fun(i32, i32) bool = __thunk_less_i32
```

thunk 把具体类型的 `fun(i32,i32) bool` 桥接到擦除后的 `less(desc, raw, raw) bool`。

## pass 管线变更

### 当前 pass 顺序

```
parse → type_alias_expand → module_merge → monomorphize → symtab → typecheck → llvm_codegen
```

### 目标 pass 顺序

```
parse → type_alias_expand → module_merge
    → symtab                        # 不变：为泛型模板建符号表
    → template_typecheck            # 新：typecheck 泛型模板（T 保持为类型参数），标注每个节点是否涉及 T
    → collect_desc_ops              # 新：基于标注后的 AST 收集描述符操作
    → erase_generics                # 新：AST 改写（签名 + 函数体），替换 generics.py 的 monomorphize
    → final_typecheck               # 对擦除后的 AST 做完整类型检查
    → llvm_codegen                  # 新增描述符 lowering + slot ABI
```

关键变更：`collect_desc_ops` 必须在 `template_typecheck` 之后运行——它依赖"这个 BinaryOp 的操作数类型是不是 T"这样的类型信息。

### generics.py 变更

`compiler/generics.py` 的 `monomorphize()` 函数 → 删除。替换为两个新 pass：

1. `collect_desc_ops(program, symtab) → {fn_name: DescSpec}`：遍历 type-annotated AST，收集每个泛型函数需要的描述符操作
2. `erase_generic_functions(program, ops_map) → program`：改写 AST——签名走 slot ABI，函数体走描述符调用

## 描述符类型在 LLVM 层的表达

描述符在 LLVM IR 里是一个 struct type：

```
; 对 sort 的描述符（需要 lt + size）
%__desc_sort = type { i32, i1 (i8*, i8*, i8*)* }
;                      ^size  ^lt: fun(*SortDesc, raw, raw) bool
```

内置 `lt` 函数（针对 i32）。注意接收 desc 参数（匹配统一 ABI，虽然 builtin lt 自身不需要 desc）：

```
define internal i1 @__nc_builtin_lt_i32(i8* %desc, i8* %a, i8* %b) {
    %va = bitcast i8* %a to i32*
    %vb = bitcast i8* %b to i32*
    %la = load i32, i32* %va
    %lb = load i32, i32* %vb
    %cmp = icmp slt i32 %la, %lb
    ret i1 %cmp
}
```

内置 `eq`、`hash`、`zero` 同理。内置函数在 `compiler/llvm_descriptor.py` 里管理（编译器生成，不经过 NC 源码）。

## 与约束族的交互

typecheck 的约束校验路径不变——`types.Ord` 仍然要求 `T` 支持 `<`。区别是校验完成后：

- **当前**：校验通过 → monomorphize 生成 `_sort_less_default__i32`，里面是 `icmp slt`
- **擦除后**：校验通过 → 生成 `_sort_less_default`（接收 `desc`），里面是 `desc.lt(a, b)`，调用端传 `__nc_builtin_lt_i32`

`types.Eq`、`types.Hash`、`types.Zero` 同理——约束校验不变，操作改走描述符。

## case 覆盖计划

按 case 驱动，逐步推进：

### 阶段 0：测量基线（已完成）
- [x] 测量当前单态化的二进制/IR 膨胀

### 阶段 1：最小链路 — `id[T](x: T): T`
- 验证 erased value ABI（slot 传递 + out-param 返回）
- 收集 `size`，改写签名（T 参数→raw slot, T 返回→out-param），改写函数体（`x` → slot 指针）
- case_170 覆盖，期望输出不变

### 阶段 2：加入 Ord — `min2[T types.Ord]`
- 收集 `lt` + `size`
- 改写 `a < b` → `desc.lt(a, b)`
- case_276 覆盖

### 阶段 3：入队 sort — 先只跑 `sort.sort[i32]`
- 收集 `lt` + `size`
- 改写 sort.nc 全部 8 个泛型函数
- `_sort_less_default` 变成描述符驱动
- `_sort_swap` 用 memcpy(desc.size)
- case_276_sort_default_i32 覆盖

### 阶段 4：sort 双类型 + 自定义 less
- `sort.sort[i32]` + `sort.sort[f64]` 同二进制 — sort 模块只编译一次
- 自定义 less 的 thunk 生成
- case_257, case_277 覆盖

### 阶段 5：泛型函数值
- `less[i32]` → thunk 生成
- case_299 覆盖

### 阶段 6：错误路径 + stdlib 回归
- 约束错误消息不变
- 所有现有 case 通过
- stdlib 全部 case 通过

### 阶段 7：泛型 struct — 不动
- case_171~173 保持通过（struct 单态化路径不动）

## 不做的

- 泛型 struct 擦除（零用例，保留当前单态化）
- `monomorphize` 关键字
- GC 引用类型 T 的 pointer bitmap / trace helper（当前 v1 不要求此能力；若 stdlib 出现 GC 指针泛型容器 case 再补）
- 运行期生成描述符（全部编译期常量）
- `desc.size` 作为可变字段（编译期常量，不可写）

## 已决问题

- **raw 是否是语言内部 TypeRef？** → 是。`raw` 只存在于编译器内部 AST/codegen 和 typecheck 内部类型系统，用户源码不可写。
- **比较器 ABI 是否统一带 desc？** → 统一。`fun(*SortDesc, raw, raw) bool`。所有 comparator（内置/自定义 thunk）都接收 desc 作为第一参数。
