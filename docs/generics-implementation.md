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
                  │   lt: fn(raw,raw)   │
                  │ }                   │
                  │    ↓ AST 改写       │
                  │ fun sort(           │
                  │   desc: *SortDesc,  │
                  │   xs: []raw,        │
                  │   less: fn(raw,raw) │
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
                  │      default_less)  │
                  └─────────────────────┘
```

## 描述符推导

编译器从泛型函数体（及其调用的子函数）收集对类型参数 `T` 的所有操作。递归规则：

### 触发操作收集的 AST 节点

| AST 节点 | 收集的操作 | 描述符字段 |
|----------|-----------|-----------|
| `a < b` 其中 a,b 类型为 T | `lt` | `lt: fun(raw, raw) bool` |
| `a > b` / `a <= b` / `a >= b`（从 `lt` 派生） | `lt` | 同上 |
| `a == b` / `a != b` 其中 a,b 为 T | `eq` | `eq: fun(raw, raw) bool` |
| `let x: T = ...` | `size` | `size: i32` |
| `x = y` 其中目标类型 T | `size` | 同上 |
| T 作为函数参数传递 | `size` | 同上 |
| T 作为函数返回值 | `size` | 同上 |
| `items[a]` 结果类型为 T | `size`（值拷贝） | 同上 |
| T 作为 slice 元素 `[]T`（出现在泛型函数签名里） | `size` | 同上 |
| 对 T 调用 `hash()` | `hash` | `hash: fun(raw) u64` |

### 收集算法

```
collect_ops(func, T) → set of ops:
  ops = {}
  for each statement/expr in func.body:
    if node is BinaryOp("<"|">"|"<="|">=") and operands typed T:
        ops.add(lt)
    if node is BinaryOp("=="|"!=") and operands typed T:
        ops.add(eq)
    if node is VariableDecl with type T:
        ops.add(size)
    if node is Assignment with target type T:
        ops.add(size)
    if node calls a function that is also generic and parameterized by T:
        ops.union(collect_ops(callee, T))
  return ops
```

### 描述符结构生成

收集完成后，编译器为泛型函数生成一个描述符 struct：

```
struct __desc_sort {
    size: i32,                              // sizeof(T)
    lt: fun(raw, raw) bool,                 // a < b（从 _sort_less_default 收集）
    // eq: 如果用了 == 才加
    // hash: 如果用了 hash() 才加
}
```

描述符 struct 在定义模块的 LLVM IR 里出现（`%__desc_sort = type { i32, i1 (i8*, i8*)* }`），调用端生成对应的 LLVM 常量。

## AST 改写规则

### 泛型函数签名改写

**改写前**（定义模块）：
```
fun sort[T types.Ord](items: []T, less: fun(T,T) bool = _sort_less_default[T]): void
```

**改写后**（定义模块，编译器内部）：
```
fun sort(desc: *SortDesc, items: []raw, less: fun(raw,raw) bool): void
```

具体规则：
1. 去掉 `type_params`。
2. 在参数列表**最前面**插入隐式参数 `desc: *SortDesc`。
3. 所有类型为 `T` 的参数 → 类型改为 `raw`。
4. 所有类型为 `T` 的返回类型 → 类型改为 `raw`。
5. `[]T` → `[]raw`。
6. `fun(T,T) bool` → `fun(raw,raw) bool`。

### 泛型函数体改写

| 原 AST | 改写后 AST |
|--------|-----------|
| `let x: T = expr` | `let x: raw = expr` + 调用端负责 |
| `let x = expr`（推导为 T） | `let x: raw = expr` |
| `a < b`（a,b 类型为 T） | `desc.lt(a, b)` → `FunctionCall(desc.lt, [a, b])` |
| `a == b` | `desc.eq(a, b)` |
| `items[a]`（items: `[]T` → `[]raw`） | 类型变为 `raw`，无额外改写 |
| `let tmp = items[a]`（值拷贝） | `let tmp: raw = __desc_memcpy_tmp(desc, items[a])` — 内部 builtin |
| `items[a] = tmp` | `__desc_memcpy_assign(desc, items[a], tmp)` — 内部 builtin |
| T 类型参数传递给非泛型 callee | 报错——类型擦除后 T 的具体类型在 callee 里不可知 |

### 内部 builtin：memcpy 操作

擦除后对 T 的值拷贝需要两个编译器内置操作：

```
# 从 raw slot 拷贝到 temp（分配 + memcpy）
__desc_memcpy(desc: *SortDesc, src: raw) → raw

# 从 raw 拷贝到 raw slot（memcpy）
__desc_memcpy_assign(desc: *SortDesc, dst: raw, src: raw) → void
```

这两个在 LLVM 层直接 lowering 为 `alloca(desc.size)` + `memcpy(desc.size)`，不经过函数调用。

### 默认参数改写

```
# 改写前
fun sort[T](..., less: fun(T,T) bool = _sort_less_default[T])

# 改写后：_sort_less_default 自身也被擦除
fun sort(desc: *SortDesc, ..., less: fun(raw,raw) bool = _sort_less_default)
# _sort_less_default 签名变为 fun _sort_less_default(desc: *SortDesc, a: raw, b: raw): bool
```

调用端省略 `less` 时，编译器插入 `_sort_less_default` 作为实参（它也在 sort 模块里，接收 desc），无需额外 thunk。

## 调用端：描述符生成

调用端看到 `sort.sort[i32](xs)`，需要生成：

### 1. 描述符常量

```
# 在调用端模块的 LLVM IR 里
@__desc_sort_i32 = private unnamed_addr constant %__desc_sort {
    i32 4,                                    ; size
    i1 (i8*, i8*)* @__nc_builtin_lt_i32      ; lt
}, align 8
```

标记 `unnamed_addr` + `linkonce_odr`，linker 自动去重。

### 2. 类型转换

- `xs: []i32` → `cast` 为 `[]raw`（data pointer bitcast + len/cap 相同）
- slice 的 data pointer：`bitcast i32* → i8*`

### 3. 调用改写

```
# 改写前
sort.sort[i32](xs)

# 改写后
sort.sort(@__desc_sort_i32, bitcast(xs.data), xs.len, xs.cap, _sort_less_default)
```

## 调用端：自定义 less 回调

用户写：
```
sort.sort[Point](pts, less = fun(a: Point, b: Point): bool { a.x < b.x })
```

编译器在调用端生成 thunk：

```
# 编译器生成的 thunk（在调用端模块）
fun __thunk_less_Point(desc: *PointDesc, a: raw, b: raw): bool {
    let pa: *Point = (*Point)(a)   # raw → Point 指针
    let pb: *Point = (*Point)(b)
    ret pa.x < pb.x
}
```

thunk 的签名匹配 sort 的 `less: fun(raw,raw) bool`。thunk 用于桥接用户闭包的 `fun(Point,Point) bool` 和 sort 期望的 `fun(raw,raw) bool`。

用户声明的闭包签名是 `fun(Point,Point) bool`，但擦除后 sort 只要 `fun(raw,raw) bool`。这里的语义和当前 `less` 回调经过函数值 thunk 是等价的。

## 调用端：泛型函数值

```
let f: fun(i32, i32) bool = less[i32]
```

擦除后：
```
let f: fun(i32, i32) bool = __thunk_less_i32  # 编译器生成
# __thunk_less_i32(a: i32, b: i32): bool { less(&__desc_less_i32, cast(raw, a), cast(raw, b)) }
```

编译器生成一个 thunk，把 `fun(i32,i32) bool` 包装成调用 `less(desc, cast(a), cast(b))`。

## pass 管线变更

### 当前 pass 顺序

```
parse → type_alias_expand → module_merge → monomorphize → symtab → typecheck → llvm_codegen
```

### 目标 pass 顺序

```
parse → type_alias_expand → module_merge 
    → collect_generic_ops      # 新 pass：为每个泛型函数收集描述符操作
    → erase_generics            # 新 pass：AST 改写（替换 generics.py 的 monomorphize）
    → symtab                    # 不变
    → typecheck                 # 泛型函数按擦除后类型检查
    → llvm_codegen              # 新增描述符 lowering
```

### generics.py 变更

`compiler/generics.py` 的 `monomorphize()` 函数 → 删除。替换为：

1. `collect_desc_ops(program) → {fn_name: set_of_ops}`：遍历泛型函数体，收集操作
2. `erase_generic_functions(program, ops_map) → program`：改写 AST，生成描述符 struct 引用

## 描述符类型在 LLVM 层的表达

描述符在 LLVM IR 里是一个 struct type：

```
; 对 sort 的描述符（需要 lt + size）
%__desc_sort = type { i32, i1 (i8*, i8*)* }
```

内置 `lt` 函数（针对 i32）：
```
define internal i1 @__nc_builtin_lt_i32(i8* %a, i8* %b) {
    %va = bitcast i8* %a to i32*
    %vb = bitcast i8* %b to i32*
    %la = load i32, i32* %va
    %lb = load i32, i32* %vb
    %cmp = icmp slt i32 %la, %lb
    ret i1 %cmp
}
```

内置 `eq` 函数同理。内置函数在 `compiler/llvm_runtime.py` 或新的 `compiler/llvm_descriptor.py` 里生成，与 ncrt 类似（编译器生成，不经过 NC 源码）。

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
- 最简单的泛型函数：无约束，只做值传递
- 只收集 `size`，只改写 `let x: T` 和返回类型
- case_170 覆盖

### 阶段 2：加入 Ord — `min2[T types.Ord]`
- 收集 `lt` + `size`
- 改写 `a < b` → `desc.lt(a, b)`
- case_276 覆盖

### 阶段 3：入队 sort — 先只跑 `sort.sort[i32]`
- 收集 `lt` + `size`
- 改写 sort.nc 全部 8 个泛型函数
- `_sort_less_default` 变成描述符驱动
- `_sort_swap` 用 `__desc_memcpy`
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
- stdlib 全部 61 个 case 通过

### 阶段 7：struct 泛型 struct — 不动
- case_171~173 保持通过（struct 单态化路径不动）

## 不做的

- 泛型 struct 擦除（零用例）
- `monomorphize` 关键字
- 跨模块描述符共享优化（linker 自动去重已足够）
- 运行期生成描述符（全部编译期常量）
- `desc.size` 作为可变字段（编译期常量，不可写）
