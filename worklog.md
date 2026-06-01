# worklog

> 主日志只保留当前事实、关键决策和原因。完整旧流水已归档到
> `docs/archive/worklog-2026-05-31-full.md`。

## 当前状态快照 (2026-06-01)

- NC 当前是 LLVM-only 编译器；旧 C 后端、`--backend` 和相关兼容入口已删除。
- 语言目标是“更好的 C”：显式、简单、GC、Go 级性能、自带构建系统。
- 模块系统采用“目录即模块”：同目录文件自动互见，跨模块必须显式 `import` 并限定访问。
- 标准库边界已从裸 builtin 收敛到显式模块；语言级 builtin 只保留少量类型/容器/数值基础能力。
- 运行时以 `ncrt` 私有 ABI 支撑 GC、字符串、slice、map、异常传播和少量启动参数入口。
- 构建目标支持 `windows-x64` 与 `linux-x64`；target 会影响 LLVM triple、产物扩展名、C support 编译和 extern 链接参数。
- 当前回归权威：`tests/test_language_cases.py`、`tests/test_stdlib.py`、项目级测试、builtin 边界测试、LLVM 后端测试和 type_ref 测试。

## 当前结构性债

- `design.md` 只应记录“我们要什么”和 why；标准库 API 细节以 `stdlib.md` 为准，互操作细节以 `c-interop.md` 为准。
- 类型标注在 public AST/pass 边界仍以字符串为主，内部已开始收敛到 `TypeRef` 工具层。
- GC 当前只在显式 `runtime.gc_collect()` 时回收，不在分配时自动触发。
- import v1 只支持一级模块名；包路径、别名导入和选择性导入都未纳入当前设计。
- FFI 当前只支持 C ABI scalar/pointer；聚合类型按值传递需要真正的目标 ABI classifier。

## worklog 记录规则

- 新工作开始时 append 一条“预备做什么 + why”。
- 工作完成时 append 一条“结果 + 验证 + 是否改变设计边界”。
- 重复测试命令、文件名清单和实现过程不放主日志；必要时放归档或 issue。
- 破坏兼容、放弃功能、设计改向必须写清楚原因。
- 已被 `design.md`、`stdlib.md`、`c-interop.md` 覆盖的说明，不在 worklog 重复维护。

## 关键历史

### 2026-05-16

- 项目初始化，代号 NC。
- 早期方向：更好的 C、GC、Go 级性能、自带构建系统。
- 建立 parser/typecheck/codegen/runtime 的多 pass 雏形，并以 case 推动能力增长。

### 2026-05-19 至 2026-05-25

- 从单文件输入推进到 source set：同目录 `.nc` 文件自动共享命名空间。
- 删除 `while`，条件循环统一为 `for condition { ... }`。
- 删除 `switch`，用表达式化 `match` 统一分支选择。
- 指针语义收紧：`*T` 非空，`?*T` nullable，`nil` 只属于 nullable pointer。
- 落地 import v1：一级同级目录模块、命名空间限定访问、导入图递归加载、cycle 报错、跨模块 `_` 私有。
- 标准输出从裸 `print` 迁移到 `import io` 后的 `io.println`，裸 `print` 不兼容。

### 2026-05-26

- GC root 正确性补强：参数、receiver、返回槽、catch/throw 值、局部变量和聚合内 GC 引用进入 root 管理。
- 新增并行 LLVM Lite 后端作为迁移起点。why：最终目标是 LLVM，不应继续扩大 C 后端能力面。

### 2026-05-27 至 2026-05-29

- LLVM 后端逐步覆盖语言主路径，并开始替代 C 后端作为回归权威。
- 新增显式泛型 v1、类型别名 v1、`runtime` 标准模块和 extern 声明。
- FFI 方向从 `extern "c"` 收敛为可选链接输入字符串；不保留旧 source 语义。

### 2026-05-30

- 函数类型标注统一为 `fun(T) R`，旧 `(T) -> R` 不兼容。
- 实现 `iface` v1：struct 通过指针 receiver 方法自动满足接口，接口值采用胖指针动态分派。
- 清理 import 绕路和类型字符串遗留，引入 `TypeRef` 工具层。
- 新增 `rune` 与字符串插值 v1。

### 2026-05-31

- 实现内建泛型 `map[K,V]`，删除旧 `map_new` 用户边界。
- 新增第一批基础 builtin：`cap`、`copy`、`clear`、`delete`、`min`、`max`、`abs`。
- 标准库边界拆到 `stdlib.md`；语言 case 与 stdlib case 拆分测试入口。
- 标准库开始向 NC 源码迁移：`fs`、`strings`、`os` 不再主要依赖编译器特判。

### 2026-06-01

- 实现 target-aware FFI/CI v1：新增 `windows-x64` / `linux-x64` 显式 target。
- 新增 `linux` 标准库模块，限定 linux-x64 可用。
- 修复 Linux CI 暴露的平台符号泄漏：未捕获异常打印改走 `ncrt` 私有 stderr shim。
- 删除 `map_has` 用户边界，改为 `m.has(k)`。why：map 操作应归属 map 类型方法，减少裸 builtin。
- 精简 `design.md` 与 `worklog.md`。why：`design.md` 只记录目标和原因，`worklog.md` 只记录当前事实、关键决策和结果；完整旧流水归档到 `docs/archive/worklog-2026-05-31-full.md`。
