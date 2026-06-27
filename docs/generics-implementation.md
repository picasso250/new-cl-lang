# 泛型实现：类型擦除 + TypeDesc

> 本文记录泛型函数的内部实现方案。用户语义边界见 `docs/generics.md`。
>
> 目标实现：泛型函数默认使用类型擦除，定义模块只编译一次；泛型 struct 保持单态化。

## 动机

当前 AST 级单态化存在结构性风险：

- 二进制膨胀：每个具体类型都会复制一套泛型函数 IR。
- 模块重复编译：调用端新增类型实参会改变定义模块的泛型实例集合，破坏模块对象缓存稳定性。
- 编译时间不可控：定义模块编译成本随调用端类型数量线性增长。

NC 的性能目标是 Go 级别，不追求 C++/Rust 式零开销模板。泛型函数默认走类型擦除；如果未来真实 hot path 需要逃逸，再由 case 推动显式 specialization 机制。

## 范围

| 项目 | 决策 |
| --- | --- |
| 泛型函数 | 默认擦除，定义模块产出一份 TypeDesc 驱动的函数 |
| 泛型 struct | 保持单态化，布局仍由具体类型实参决定 |
| 已实例化泛型函数值 | 调用端生成 typed thunk，桥接到 erased 函数 |
| 普通泛型直接调用 | 调用点直接生成 erased call，不经 thunk |
| extern 泛型 | 不支持 |
| iface 泛型方法 | 不支持 |
| 未实例化泛型函数模板值 | 不支持 |

## 核心模型

### TypeDesc 是类型专属

描述符按具体类型生成，不按泛型函数生成。`id[i32]`、`min2[i32]`、`sort.sort[i32]` 复用同一个 `TypeDesc[i32]`。

固定布局：

```text
TypeDesc {
  size: i32
  align: i32
  copy: fun(desc: *TypeDesc, dst: raw, src: raw)
  zero: fun(desc: *TypeDesc, dst: raw)
  eq: fun(desc: *TypeDesc, a: raw, b: raw) bool
  lt: fun(desc: *TypeDesc, a: raw, b: raw) bool
  hash: fun(desc: *TypeDesc, a: raw) u64
  trace: fun(desc: *TypeDesc, slot: raw)
}
```

不支持的能力字段填 trap helper，不填 null。用户错误仍必须在 typecheck 阶段报错；trap 只作为编译器内部误调用的最后防线。

所有可作为值的 sized 类型都必须有 `copy` 和 `trace`。`zero`、`eq`、`lt`、`hash` 可按类型能力填真实 helper 或 trap helper。

泛型 struct 单态化后的具体类型同样生成自己的 TypeDesc，例如 `Box[i32]` 是一个普通具体类型。

### raw 是 slot pointer

`raw` 是编译器内部 TypeRef，用户源码不可写。LLVM 层 lower 为 `i8*`，语义是“指向一个 T 值 slot 的指针”。

- `T` 参数：调用端提供 slot，callee 接收 raw。
- `T` 返回值：调用端提供 ret slot，callee 写入。
- `let tmp: T = x`：callee 分配 slot，再调用 `desc.copy(desc, tmp, x)`。
- `a < b`：调用 `desc.lt(desc, a, b)`。
- `a == b`：调用 `desc.eq(desc, a, b)`。

erased IR 中不存在按值 `T`。

### 容器保持 opaque

`[]T`、`[N]T`、`map[K,V]` 在 erased 泛型函数中不改写成 `[]raw` 或 raw 指针数组。容器值保持句柄/对象，由 descriptor-aware helper 访问元素或 entry。

示例 helper 形态：

```text
slice_len(slice_handle) -> i64
slice_elem_ptr(type_desc_T, slice_handle, index) -> raw

array_len(array_handle) -> i64
array_elem_ptr(type_desc_T, array_handle, index) -> raw

map_has(map_handle, key_desc, value_desc, key_raw) -> bool
map_get_ptr(map_handle, key_desc, value_desc, key_raw) -> raw
map_set(map_handle, key_desc, value_desc, key_raw, value_raw)
```

容器内部布局不因泛型擦除改变。`map` 的 runtime descriptor 最终应以 `TypeDesc[K]` 和 `TypeDesc[V]` 为核心，复用同一套 `eq/hash/copy/trace/zero` 能力。

## ABI

### 泛型函数签名

每个类型参数传一个 `TypeDesc*`，按类型参数声明顺序放在最前面。只有返回类型涉及类型参数时才增加 erased out-param；out-param 放在所有 TypeDesc 之后、用户参数之前。

```text
fun id[T](x: T): T
=> id(desc_T, ret_slot, x_slot) -> void

fun less2[T types.Ord](a: T, b: T): bool
=> less2(desc_T, a_slot, b_slot) -> bool

fun choose[A, B](flag: bool, a: A, b: B): A
=> choose(desc_A, desc_B, ret_A_slot, flag, a_slot, b_slot) -> void
```

泛型递归调用复用当前 TypeDesc。递归泛型函数仍要求显式返回类型，避免返回类型推导成环。

### 函数参数和回调

`fun(T, T) bool` 这样的参数在 erased 函数内部改写为：

```text
fun(desc_T: *TypeDesc, a: raw, b: raw) bool
```

因此 comparator、默认 less、自定义 less thunk 都使用同一 ABI。泛型函数体内禁止把 erased `T` slot 传给需要具体 typed ABI 的 callable；允许传给同样 erased 的泛型函数、erased 回调或 TypeDesc helper。

### 默认参数

默认参数不改变函数 ABI。调用端省略默认参数时，编译器在调用点补齐 erased ABI 下的普通实参。

```nc
fun sort[T types.Ord](items: []T, less: fun(T, T) bool = _sort_less_default[T])
```

内部 ABI 始终包含 `less`：

```text
sort(desc_T, items_handle, less_erased)
```

用户写 `sort[i32](xs)` 时，调用点补齐为：

```text
sort(type_desc_i32, xs_handle, _sort_less_default_erased)
```

### 泛型函数值

已实例化泛型函数作为函数值时，调用端生成 typed thunk：

```nc
let f: fun(i32) i32 = id[i32]
```

内部：

```text
__thunk_id_i32(x: i32): i32 {
  x_slot = alloca i32
  store x -> x_slot
  ret_slot = alloca i32
  id(type_desc_i32, ret_slot, x_slot)
  return load ret_slot
}
```

普通直接调用 `id[i32](x)` 不经 thunk，调用点直接生成 erased call。

## TypeDesc 能力规则

约束校验仍在 typecheck 阶段完成。TypeDesc 字段只是实现载体。

- `types.Eq`：要求 `eq` 可用。
- `types.Ord`：要求 `lt` 可用；不隐含 `Eq`。
- `types.Hash`：要求 `hash` 和 `eq` 可用；隐含 `Eq`。
- `types.Zero`：要求 `zero` 可用。

`< <= > >=` 在泛型 erased lowering 中只依赖 `lt`：

```text
a < b   => desc.lt(desc, a, b)
a > b   => desc.lt(desc, b, a)
a <= b  => !desc.lt(desc, b, a)
a >= b  => !desc.lt(desc, a, b)
```

struct 的 `Ord` 只由合法 `__lt__` 提供。struct 的 `Eq` 和 `Hash` 由字段递归自动生成，不开放 `__eq__`、`__ne__` 或 `__hash__`。

## GC 与 typed root

erased T slot 可能包含 GC 引用。所有可能跨 safepoint 存活的 erased slot 必须以 typed root 形式注册：

```text
(slot_ptr, type_desc_ptr)
```

GC 标记 typed root 时调用：

```text
type_desc.trace(type_desc, slot_ptr)
```

无引用类型的 `trace` 是 no-op。`str`、pointer、nullable pointer、slice、map、array handle、struct with refs 等由各自 helper 追踪内部引用。

## pass 管线

目标 pass 顺序：

```text
parse
  -> type_alias_expand
  -> module_merge
  -> symtab
  -> template_typecheck       # T 保持为类型参数，标注 T-use
  -> collect_type_desc_needs  # 基于 typecheck 结果收集 copy/zero/eq/lt/hash/trace 需求
  -> erase_generic_functions  # 签名和函数体改写
  -> final_typecheck
  -> llvm_codegen
```

`collect_type_desc_needs` 依赖类型信息，不能放在 template typecheck 之前。

## 实施阶段

1. 建立固定 `TypeDesc` LLVM 布局和内建类型 helper。
2. 将当前 identity/min2 白名单擦除改为统一泛型函数 erased ABI。
3. 引入 erased slot typed root，保证 `id[str]`、`id[*T]` 等 GC 正确。
4. 容器访问改为 opaque helper：slice/array/map 元素访问返回 raw。
5. 泛型函数互调复用同一个 TypeDesc。
6. 默认参数和 comparator 改写到 erased ABI。
7. 已实例化泛型函数值生成 typed thunk。
8. map runtime descriptor 逐步收敛到 `TypeDesc[K]` / `TypeDesc[V]`。

## 不做的

- 泛型 struct 擦除。
- primary 类型自动单态化。
- 接口约束。
- 约束组合语法。
- extern 泛型、iface 泛型方法、泛型函数模板值。
- 运行期生成 TypeDesc。
- `monomorphize` / `specialize` 用户语法。
