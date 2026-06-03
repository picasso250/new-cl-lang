# NC 泛型

本文记录泛型 v1 的用户边界和当前类型属性矩阵。`design.md` 只保留原则和 why；本文件用于承载约束族细节。

## 泛型 v1

- 泛型函数和泛型 struct 使用显式类型参数：`fun id[T](x: T): T`、`struct Box[T] { value: T }`。
- 调用和构造必须显式写类型实参：`id[i32](1)`、`Box[str] { value: "x" }`。
- 默认约束是 `any`。
- 编译器识别的标准约束名：`types.Eq`、`types.Ord`、`types.Hash`、`types.Zero`。
- `types.Cmp` 不是当前语言边界。

## 约束族

- `types.Eq`：支持 `==` / `!=` 的类型。
- `types.Ord`：支持 `<` / `>` / `<=` / `>=` 的类型，当前为数值类型。
- `types.Hash`：可作为 `map[K,V]` key 的类型，要求 equality 是稳定等价关系；float 不满足。
- `types.Zero`：有零值的类型。

## 类型属性矩阵

| 类型 | Eq | Ord | Hash | Zero | 说明 |
| --- | --- | --- | --- | --- | --- |
| signed/unsigned integer | yes | yes | yes | yes | 包括 `i8..i64`、`u8..u64` |
| float | yes | yes | no | yes | `f32`、`f64` 不可作 map key |
| `bool` | yes | no | yes | yes |  |
| `str` | yes | no | yes | yes | 当前不纳入默认排序 |
| `rune` | yes | no | yes | yes | 不当作普通 numeric 使用 |
| `enum` | yes | no | yes | yes |  |
| `*T` | yes | no | yes | no | 非空指针没有零值 |
| `?*T` | yes | no | yes | yes | nil 是零值 |
| `[]T` | no | no | no | yes | slice 零值为空/nil slice |
| `[N]T` | no | no | no | if `T: Zero` | 数组不参与 equality 或 map key |
| `map[K,V]` | no | no | no | yes | map 零值为空/nil map |
| `fun(T) R` | no | no | no | yes | 函数值不参与 equality |
| `iface` | no | no | no | yes | 接口值不参与 equality |
| `struct` | if all fields Eq | no | if all fields Hash | if all fields Zero | 字段递归判断 |
| `void` | no | no | no | no | 不能作为值类型 |

## 标准库使用

- `sort.sort[T types.Ord](items: []T)` 使用 `types.Ord`。
- `map[K,V]` 的 key 规则等价于 `K: types.Hash`。
- `map[K,V]` 的 value 规则要求 `V` 是 sized 且满足 `types.Zero`。
