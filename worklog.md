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

- 2026-06-01: 预备补齐标准库实用核心：新增 strconv/math/sort，扩展 strings。why：标准库边界已显式模块化，需要把常用转换、字符串、数学、排序能力从 case 推进到可依赖 API。

- 2026-06-01: 已完成标准库实用核心：新增 strconv/math/sort，扩展 strings，并同步 stdlib/design 文档。验证：tests/test_stdlib.py、tests/test_language_cases.py、pytest test_llvm_backend/test_builtin_boundary/test_type_ref/test_projects 均通过；项目 import 测试改用非保留模块名 calc，以符合标准库模块名保留规则。

- 2026-06-03: 预备实现 struct 值结构相等：同类型 struct 的 `==` / `!=` 按字段递归比较，同时收紧不可比较类型的 typecheck。why：当前前端会放行同类型 struct 比较，但 LLVM 后端没有聚合比较语义，`struct ==` case 需要明确语言能力并避免后端崩溃。

- 2026-06-03: 已实现 struct 值结构相等：typecheck 新增递归可比较性检查，LLVM 后端按字段递归 lowering `==` / `!=`，并明确拒绝 slice、数组、map、函数值、接口值等不可比较类型。已同步 design.md，新增 case_250~257 覆盖正向和错误路径。验证：`python tests/test_language_cases.py` 通过 214/214；`python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py -q` 通过 61 passed, 1 skipped；`python tests/test_stdlib.py` 通过 51/51；`python -m pytest tests/test_projects.py -q` 通过 26/26。

- 2026-06-03: 预备优化 map 实现：质疑所有 key/value 统一 nc_val 装箱，改为 typed map descriptor；key 收敛为非 float hash-comparable，value 放宽为任意有零值 sized 类型，并补 GC 正确性 case。why：当前装箱 ABI 阻碍 map 扩展与性能，且 float key 语义和语言比较不一致。

- 2026-06-03: 已优化 map 实现：runtime map ABI 从统一 nc_val 装箱改为 typed descriptor + typed bytes；key 改为非 float hash-comparable，支持 struct/enum/pointer/nullable pointer 等；value 放宽为任意有零值 sized 类型，并补充 struct value 与 GC 保活 case。同步 design.md/stdlib.md，map ABI size_of 变为 40。验证：python tests/test_stdlib.py；python tests/test_language_cases.py；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q。

- 2026-06-03: 预备实现显式类型默认参数：支持 fun foo(a: T, b: T = value) 并在调用端补齐尾部默认实参，不改变函数 ABI、函数类型或闭包调用 ABI。why：默认参数是常见函数 ergonomics case，但必须保持 NC 参数显式类型和调用语义可预测。

- 2026-06-03: 已实现显式类型默认参数：函数/方法参数支持 name: T = expr，默认参数必须位于尾部，普通函数/方法调用在 typecheck 阶段补齐缺失尾部实参；默认值按声明处上下文检查，可引用前序参数和可见全局符号；extern、iface、函数表达式/函数类型不支持默认参数，ABI 不变。同步 design.md，新增 case_258~270 覆盖正向、泛型、方法和错误路径。验证：python tests/test_language_cases.py 通过 227/227；python tests/test_stdlib.py 通过 56/56；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 87 passed, 1 skipped。

- 2026-06-03: 预备实现 map 遍历：支持 for key, value in map[K,V]，保持 range 和 slice 遍历既有语义，不增加单变量 map 遍历。why：typed map 已落地，需要 case 驱动补齐自然遍历能力。

- 2026-06-03: 已实现 map 遍历：typecheck 支持 for key, value in map[K,V] 并保持 range/slice 语义；ncrt 新增 __nc_map_next typed copy helper；LLVM 后端按 cursor 调用 helper 并 root key/value slot。同步 design.md/stdlib.md，新增 case_271~275 覆盖基础、非字符串、struct copy、break 和错误路径。验证：python tests/test_language_cases.py；python tests/test_stdlib.py；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q。

- 2026-06-03: 预备实现窄版泛型约束与默认排序：新增编译器识别的 `types.Cmp` 约束，支持 `sort.sort[T types.Cmp]([]T)` 对有序数值类型原地稳定排序，暂不引入完整 type-set 语法，也暂不把 `str` 纳入有序类型。why：sort 默认排序需要比较约束，但当前泛型 v1 只有 any，先以具体 case 推动最小约束能力。

- 2026-06-03: 已实现窄版泛型约束与默认排序：新增 `types.Cmp` 编译器约束模块名，泛型参数支持 `T types.Cmp` 并在单态化时校验类型实参；`types.Cmp` 当前限定为数值类型，`str` 和 struct 明确拒绝。`sort` 新增 `sort.sort[T types.Cmp]` 原地稳定升序排序，保留 `sort.by` 用于自定义比较。同步 design.md/stdlib.md，新增 case_276~279 与泛型约束 case。验证：python tests/test_stdlib.py；python tests/test_language_cases.py；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q。
