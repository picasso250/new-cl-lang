# C 互操作 — 任务书

### 一、`runtime` 内置模块

`runtime` 是一级内置模块，同 `io`：不走目录、不参与 cycle，优先于真实同级 `runtime/` 目录。v1 只公开稳定调试/运行时 API：

```nc
import runtime

runtime.gc_collect()
let n = runtime.gc_live()
```

其他 `ncrt` helper 是编译器私有 ABI，不通过 `runtime` 暴露。裸 `gc_collect()` / `gc_live()` 不保留兼容。

### 二、`extern` 块

用户自定 C 函数声明。来源在块头部指定，块内是函数签名。

```nc
extern "c" {
    fun putchar(c: i32): i32
    fun strlen(p: *u8): u64
}
```

- 块头部 v1 只支持 `"c"`；其他字符串直接报错：`extern v1 only supports "c"`
- 块内只允许无函数体的函数签名；省略返回类型表示 `void`
- 编译器为块内每个 `fun` 生成 LLVM `declare`，链接命令暂不新增库参数，依赖当前 MinGW/GCC 默认可解析的 C runtime 符号
- 支持类型限定为 C ABI scalar/pointer：`i8/i16/i32/i64/u8/u16/u32/u64/f32/f64/bool/*T/?*T/void`
- C 字符串用 `*u8`，不做 str ↔ char* 自动转换
- 调用期间 GC 参数自动 root，调用后退栈
- 错误处理手动：函数返回什么，用户检查什么，不自动转 throw

v1 不做：`.c`、`.dll`、`.lib`、varargs、回调、头文件解析、extern struct、聚合类型按值传递、泛型 extern、extern iface、`str`/slice/array/struct/enum/function value/`nc_map`。
