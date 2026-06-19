# NC 标准库与语言内建边界

本文记录用户可依赖的标准库模块和语言级内建。`runtime/ncrt.*` 中的 helper 是编译器私有 ABI，除本文明确列出的 `runtime` 模块 API 外，不作为用户可依赖标准库 API。

## 原则

- 标准库模块必须显式 `import` 后用限定名访问，例如 `import io` 后调用 `io.println(...)`。
- 语言级 builtin 不需要 `import`，属于语法或类型系统边界。
- 不向前兼容未进入当前设计的旧 API。

## import 规则

- 标准库一级内置模块名：`io`、`fs`、`os`、`runtime`、`strings`、`strconv`、`math`、`sort`、`types`、`linux`。
- `import foo` 优先解析同级目录模块；内置标准模块名保留，导入这些名字时不查找同级目录。
- 编译器随附的 NC 标准库源码模块会递归加载自身 import；用户同级目录仍不能覆盖保留标准模块名。
- 标准库源码模块可带同名 C support 文件：若实际导入 `stdlib/<name>/<name>.nc` 所在模块，且存在 `stdlib/<name>/<name>.c`，构建系统会自动编译并链接该 C 文件。该机制只对编译器随附标准库生效，不扩展到用户项目的 `foo/foo.c`。
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

`exists` 对不存在返回 `false`；其他操作失败会 `err` 字符串错误。`mkdir` 只创建单级目录，`rename` 在目标已存在时失败。

当前 `fs` 的公开 API 由编译器随附的 `stdlib/fs/fs.nc` 实现。`read_bytes` 返回原始字节；`read_file` 是文本便利层，等价于 `str(fs.read_bytes(path))`。需要平台或 C runtime 差异隔离的路径操作通过同目录 `stdlib/fs/fs.c` 暴露的私有 shim 实现；用户只写普通 `extern { ... }`，不需要在 NC 源码里声明对象文件或库路径。

### os

- `os.args(): []str`：返回包含程序自身路径的参数列表。
- `os.getenv(name): str`：环境变量不存在时返回 `""`。
- `os.has_env(name): bool`：区分变量不存在和值为空字符串。
- `os.cwd(): str`：失败时 `err "os.cwd failed"`。
- `os.exit(code)`：立即退出进程，不运行 NC `defer`。

v1 不提供 `os.setenv`、`os.unsetenv`、`os.chdir`。

当前 `os` 的公开 API 由编译器随附的 `stdlib/os/os.nc` 实现。`args` 通过 `ncrt` 私有启动参数 helper 读取 LLVM `main(argc, argv)` 保存的参数；`getenv`/`has_env`/`exit` 通过 extern alias 调用 C runtime 符号，`cwd` 通过同目录 `stdlib/os/os.c` 私有 shim 在 Windows 调 `_getcwd`、Linux 调 `getcwd`。

### linux

- `linux.getpid(): i32`
- `linux.write(fd: i32, data: []u8): i64`
- `linux.write_str(fd: i32, data: str): i64`

`linux` 只在 `--target linux-x64` 下可导入；在 Windows target 下导入会编译报错。当前实现由 `stdlib/linux/linux.nc` 调用同目录 `linux.c` 私有 shim，shim 在 C 侧使用 Linux x64 用户态 `syscall`，暂不暴露 NC varargs 或指针整数转换能力。

### runtime

- `runtime.gc_collect()`
- `runtime.gc_live(): i32`

这是当前唯一公开的运行时调试 API。

### strings

- `strings.contains(s, sub): bool`
- `strings.starts_with(s, prefix): bool`
- `strings.ends_with(s, suffix): bool`
- `strings.index(s, sub): i32`
- `strings.last_index(s, sub): i32`
- `strings.count(s, sub): i32`
- `strings.repeat(s, n): str`
- `strings.replace_all(s, old, new): str`
- `strings.trim_prefix(s, prefix): str`
- `strings.trim_suffix(s, suffix): str`
- `strings.trim_space(s): str`

这些函数是字节级字符串 API，参数均为 `str`。`index` 返回首个匹配的 UTF-8 字节下标，`last_index` 返回最后一个匹配的 UTF-8 字节下标，未找到返回 `-1`。空子串规则为 contains/starts_with/ends_with 返回 `true`，index 返回 `0`，last_index 返回 `len(s)`，count 返回 `len(s)+1`。`replace_all` 的 `old` 为空时会 `err "strings.replace_all empty old"`。

当前 `strings` 的公开 API 由编译器随附的 `stdlib/strings/strings.nc` 以纯 NC 实现。

### strconv

- `strconv.atoi(s): i32`
- `strconv.itoa(n): str`
- `strconv.parse_i32(s): i32`
- `strconv.parse_f64(s): f64`
- `strconv.format_i32(n): str`
- `strconv.format_f64(n): str`

`parse_i32` 支持可选 `+`/`-` 和十进制数字；空串、只有符号、非数字字符和溢出都会 `err "strconv.parse_i32 failed"`。`parse_f64` 支持可选符号、整数部分和小数部分，至少需要一个数字；v1 不支持 exponent，非法输入会 `err "strconv.parse_f64 failed"`。

### math

- `math.sqrt(x): f64`
- `math.pow(x, y): f64`
- `math.sin(x): f64`
- `math.cos(x): f64`
- `math.tan(x): f64`
- `math.floor(x): f64`
- `math.ceil(x): f64`
- `math.round(x): f64`
- `math.exp(x): f64`
- `math.log(x): f64`
- `math.pi(): f64`
- `math.e(): f64`

当前 `math` 的公开 API 由 `stdlib/math/math.nc` 调用同目录 `math.c` 私有 shim 实现，用 C runtime/libm 隔离平台差异。

### sort

- `sort.sort[T types.Ord](items: []T)`
- `sort.by[T](items: []T, less: fun(T, T) bool)`
- `sort.is_sorted_by[T](items: []T, less: fun(T, T) bool): bool`

`sort.sort` 对 `types.Ord` 类型原地不稳定升序排序。`sort.by` 原地不稳定排序；`less(a, b)` 返回 `true` 表示 `a` 应排在 `b` 前。相等元素的原相对顺序不保证保留。

### types

- `types.Eq`：泛型约束，支持 `==` / `!=` 的类型。
- `types.Ord`：泛型约束，支持 `<` / `>` / `<=` / `>=` 的类型，当前为数值类型。
- `types.Hash`：泛型约束，可作为 `map` key 的类型。
- `types.Zero`：泛型约束，有零值的类型。

这些约束是编译器识别的约束名，不是运行时值类型。完整类型属性矩阵见 `generics.md`。

## 语言级内建

- `len(x)`：支持 `str`、`[]T`、`map[K,V]`。
- `cap(s)`：支持 `[]T`，返回 slice 当前容量。
- `append(s, value)`：支持 `[]T`，返回追加后的 slice。
- `copy(dst, src)`：要求两侧为相同 `[]T`，复制 `min(len(dst), len(src))` 个元素，返回复制数量。
- `clear(x)`：支持 `[]T` 和 `map[K,V]`；slice 清零当前 `len` 范围元素，map 清空条目。
- `delete(m, k)`：支持 `map[K,V]`，删除存在的 key；缺失 key 无效果。
- `min(a, b)` / `max(a, b)`：要求两侧为完全相同的数值类型，返回同类型。
- `abs(x)`：支持有符号整数与浮点类型，返回同类型。
- `size_of(T)`：编译期内建表达式，只接受类型实参，返回 `u64`。
- `map[K,V]()`：内建泛型 map 构造形式。
- 显式转换：`str(...)`、`i32(...)`、`rune(...)` 等目标类型函数式转换。
- `str([]u8)` 会复制字节到新的 `str` buffer 并补 NUL；v1 不验证 UTF-8。
- `str(*i8)` / `str(?*i8)` / `str(*u8)` / `str(?*u8)` 会复制 NUL 结尾 C 字符串到新的 `str`；nil 返回空字符串。

## str C interop

- `s.c_str(): *i8`：返回指向 `str` 内容的 NUL 终止 C 字符串指针。
- `len(s)` 仍是 NC 字符串长度的权威；字符串内部允许 `NUL` 字节，C API 通过 `c_str()` 消费时会按 C 字符串规则在首个 `NUL` 处截断。
- NC 创建的字符串 buffer 保证 `ptr[len] == 0`；空字符串或 `{ null, 0 }` 零值经 `c_str()` 返回共享空 C 字符串指针。

## map 边界

- `map[K,V]` 是内建泛型 map 类型，构造语法为 `map[K,V]()`.
- key 必须是 hash-comparable：非 float 的可比较类型，包括整数、bool、rune、str、enum、指针、nullable pointer，以及字段递归满足该规则的 struct。
- value 必须是有零值的 sized 类型；`void`、非空指针和递归包含无零值字段的 struct 不可作为 value。
- `m[k]` 要求 `k: K`，返回 `V`；缺失 key 返回 `V` 的零值。
- `m[k] = v` 要求 `v: V`；复合赋值按 `V` 类型复用对应运算符规则。
- 遍历使用 `for key, value in m {}`；遍历顺序不保证稳定。
- `m.has(k)` 要求 `k: K`，返回 `i32`。
- `len(m)` 返回 map 当前条目数，类型为 `i32`。

## size_of(T)

`size_of(T)` 返回当前 LLVM/ncrt ABI 下类型 `T` 的运行时布局大小：基础标量按实际宽度，`str` 为 16，`[]T` 为 24，`map[K,V]` 为 40，函数值与接口值为 16，指针与 nullable pointer 为 8，enum/rune 为 4，数组按元素 ABI stride 乘长度，struct 按字段偏移、padding 和最终对齐计算。

`size_of(void)` 非法；命名/限定类型必须存在且遵守跨模块 `_` 私有可见性；嵌套类型组件会递归校验。
