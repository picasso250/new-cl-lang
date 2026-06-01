# NC 标准库与语言内建边界

本文记录用户可依赖的标准库模块和语言级内建。`runtime/ncrt.*` 中的 helper 是编译器私有 ABI，除本文明确列出的 `runtime` 模块 API 外，不作为用户可依赖标准库 API。

## 原则

- 标准库模块必须显式 `import` 后用限定名访问，例如 `import io` 后调用 `io.println(...)`。
- 语言级 builtin 不需要 `import`，属于语法或类型系统边界。
- 不向前兼容旧裸 API；例如裸 `print(...)`、`read_file(...)`、`gc_collect()` 都不是当前语言边界。

## import 规则

- 标准库一级内置模块名：`io`、`fs`、`os`、`runtime`、`strings`。
- `import foo` 优先解析同级目录模块；内置标准模块名保留，导入这些名字时不查找同级目录。
- 内置标准模块不参与用户模块 import cycle。
- 语言级 builtin 不需要 import。

## 标准库模块

### io

- `io.print(value)`：输出值，不追加换行。
- `io.println(value)`：输出值并追加换行。
- 支持输出 `str`、`rune`、`bool`、有符号整数、无符号整数和浮点数。`rune` 按对应 UTF-8 字符输出。

### fs

- `fs.read_file(path): str`
- `fs.read_bytes(path): []u8`
- `fs.write_file(path, content)`
- `fs.exists(path): bool`
- `fs.remove(path)`
- `fs.rename(old_path, new_path)`
- `fs.mkdir(path)`

`exists` 对不存在返回 `false`；其他操作失败会 `throw` 字符串错误。`mkdir` 只创建单级目录，`rename` 在目标已存在时失败。

当前 `fs` 的公开 API 由编译器随附的 `stdlib/fs/fs.nc` 实现。`read_bytes` 返回原始字节；`read_file` 是文本便利层，等价于 `str(fs.read_bytes(path))`。读写文件的流程在 NC 源码中调用 C stdio extern；`exists/remove/rename/mkdir` 通过单独链接的 `ncfs` 平台 support 对象提供窄 C shim，不属于 `ncrt` 私有 ABI。

### os

- `os.args(): []str`：返回包含程序自身路径的参数列表。
- `os.getenv(name): str`：环境变量不存在时返回 `""`。
- `os.has_env(name): bool`：区分变量不存在和值为空字符串。
- `os.cwd(): str`：失败时 `throw "os.cwd failed"`。
- `os.exit(code)`：立即退出进程，不运行 NC `defer`。

v1 不提供 `os.setenv`、`os.unsetenv`、`os.chdir`。

### runtime

- `runtime.gc_collect()`
- `runtime.gc_live(): i32`

这是当前唯一公开的运行时调试 API。裸 `gc_collect()` / `gc_live()` 不是 builtin。

### strings

- `strings.contains(s, sub): bool`
- `strings.starts_with(s, prefix): bool`
- `strings.ends_with(s, suffix): bool`
- `strings.index(s, sub): i32`

这些函数是无分配字节级字符串查询 API，参数均为 `str`。`index` 返回首个匹配的 UTF-8 字节下标，未找到返回 `-1`。空子串规则为 contains/starts_with/ends_with 返回 `true`，index 返回 `0`。

## 语言级内建

- `len(x)`：支持 `str`、`[]T`、`map[K,V]`。
- `cap(s)`：支持 `[]T`，返回 slice 当前容量。
- `append(s, value)`：支持 `[]T`，返回追加后的 slice。
- `copy(dst, src)`：要求两侧为相同 `[]T`，复制 `min(len(dst), len(src))` 个元素，返回复制数量。
- `clear(x)`：支持 `[]T` 和 `map[K,V]`；slice 清零当前 `len` 范围元素，map 清空条目。
- `delete(m, k)`：支持 `map[K,V]`，删除存在的 key；缺失 key 无效果。
- `min(a, b)` / `max(a, b)`：要求两侧为完全相同的数值类型，返回同类型。
- `abs(x)`：支持有符号整数与浮点类型，返回同类型。
- `map_has(m, k)`：要求 `m: map[K,V]` 且 `k: K`，返回 `i32`。
- `size_of(T)`：编译期内建表达式，只接受类型实参，返回 `u64`。
- `map[K,V]()`：内建泛型 map 构造形式。
- 显式转换：`str(...)`、`i32(...)`、`rune(...)` 等目标类型函数式转换。
- `str([]u8)` 会复制字节到新的 `str` buffer 并补 NUL；v1 不验证 UTF-8。

## str C interop

- `s.c_str(): *i8`：返回指向 `str` 内容的 NUL 终止 C 字符串指针。
- `len(s)` 仍是 NC 字符串长度的权威；字符串内部允许 `NUL` 字节，C API 通过 `c_str()` 消费时会按 C 字符串规则在首个 `NUL` 处截断。
- NC 创建的字符串 buffer 保证 `ptr[len] == 0`；空字符串或 `{ null, 0 }` 零值经 `c_str()` 返回共享空 C 字符串指针。

## map 边界

- `map[K,V]` 是内建泛型 map 类型，构造语法为 `map[K,V]()`.
- v1 只支持标量 key/value：`i8/i16/i32/i64/u8/u16/u32/u64/f32/f64/bool/rune/str`。
- `m[k]` 要求 `k: K`，返回 `V`；缺失 key 返回 `V` 的零值。
- `m[k] = v` 要求 `v: V`；复合赋值按 `V` 类型复用对应运算符规则。
- `len(m)` 返回 map 当前条目数，类型为 `i32`。
- `map_new()`、裸 `nc_map` 和旧字符串专用 map helper 不是语言边界。

## size_of(T)

`size_of(T)` 返回当前 LLVM/ncrt ABI 下类型 `T` 的运行时布局大小：基础标量按实际宽度，`str` 为 16，`[]T` 为 24，`map[K,V]` 为 32，函数值与接口值为 16，指针与 nullable pointer 为 8，enum/rune 为 4，数组按元素 ABI stride 乘长度，struct 按字段偏移、padding 和最终对齐计算。

`size_of(void)` 非法；命名/限定类型必须存在且遵守跨模块 `_` 私有可见性；嵌套类型组件会递归校验。
