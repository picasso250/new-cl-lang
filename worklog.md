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

- 2026-06-03: 预备补齐 types 约束族：将泛型约束从单一 types.Cmp 替换为 types.Eq/types.Ord/types.Hash/types.Zero，并新增泛型类型属性矩阵文档。why：当前 Eq/Ord/Hash/Zero 能力已经在比较、排序、map key/value 语义中分散存在，需要收敛成可复用的标准约束边界。

- 2026-06-03: 已补齐 types 约束族：删除公开 types.Cmp 边界，新增 types.Eq/types.Ord/types.Hash/types.Zero，sort.sort 改用 types.Ord；泛型实例化保留原始约束元数据并在 typecheck 阶段按符号表递归校验 Eq/Hash/Zero，新增 docs/generics.md 记录完整类型属性矩阵。同步 design.md/stdlib.md，新增 case_277~284 覆盖约束族和旧名拒绝。验证：python tests/test_language_cases.py 通过 241/241；python tests/test_stdlib.py 通过 60/60；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 87 passed, 1 skipped。

- 2026-06-18: 预备替换异常模型为 err 错误返回并迁移 ret。why：当前 throw/try/catch 与 defer 的双重异常语义冲突，改为显式可错返回并删除旧 return 关键字，保持 NC 错误路径显式、可预测。

- 2026-06-18: 已替换异常模型为 err 错误返回并迁移 ret：删除源码 throw/try/catch/return 边界，新增内建 error、err、??/!!/is err，普通函数和 struct 方法可错性由函数体推导；可错函数 LLVM ABI 改为状态返回 + 隐藏 out 参数，defer 中禁止 err 和 ??，旧 ncrt setjmp/throw 通道已删除。同步 design.md/stdlib.md，新增 case_285~291 覆盖传播、必须成功、裸调用错误、defer 禁止和方法可错。验证：python tests/test_language_cases.py；python tests/test_stdlib.py；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q。

- 2026-06-18: 预备做 typechecker 第一轮等价重构：从 compiler/typecheck.py 抽出低状态依赖的类型规则到独立模块，保留 infer_types public 入口和现有错误文案，不新增语言能力。why：typecheck 已膨胀为 1300+ 行闭包，比较性、零值、map、size_of、约束和 extern ABI 规则适合作为低风险第一刀。

- 2026-06-18: 已完成 typechecker 第一轮等价重构：新增 compiler/type_rules.py 承接类型谓词、比较/哈希/零值递归规则、map/size_of 校验、泛型约束校验和 extern ABI 判断；compiler/typecheck.py 保留 infer_types 入口与 AST 遍历/作用域/return/fallible 状态逻辑，行为边界不变，design.md 无需更新。验证：python -m py_compile compiler/typecheck.py compiler/type_rules.py；python tests/test_language_cases.py 通过 248/248；python tests/test_stdlib.py 通过 60/60；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 87 passed, 1 skipped。

- 2026-06-18: 预备清理测试噪音：删除明确重复的 case，旧 throw/try/catch 命名测试改为 err 命名并保留覆盖，同时精简 LLVM-only 后重复的项目级测试。why：当前错误模型已迁移到 err，测试名和重复 case 会干扰后续 case 驱动判断，但不应降低回归覆盖。

- 2026-06-18: 已完成测试噪音清理：删除 4 个重复/弱覆盖 language case，旧 throw 命名 case 改为 err 命名并保留覆盖，LLVM-only 后重复的项目级聚合测试已删除，相关 Python 测试函数改为 err 命名。design.md 无需更新。验证：python tests/test_language_cases.py 通过 244/244；python tests/test_stdlib.py 通过 60/60；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 86 passed, 1 skipped；rg -n "throw|try|catch|throws" test_cases stdlib_cases tests 仅剩 Python 语法 try 和非异常语义函数名命中。

- 2026-06-18: 预备实现 Go 式 struct 嵌入和窄版 struct 运算符重载：支持 `struct B { A }` 的字段/方法提升与 `__add__` 等特殊方法。why：需要用组合形式覆盖 Go-like “继承” case，同时保持 `==`/map/hash 语义稳定。

- 2026-06-18: 已实现 Go 式 struct 嵌入和窄版 struct 运算符重载：匿名字段作为真实字段保存并支持 `b.A`、字段/方法提升、通过提升方法满足 iface；方法 receiver 支持跨模块限定类型；struct 的 `+ - * / % < <= > >=` 可通过 `__add__` 等指针 receiver 特殊方法重载，`==`/`!=` 仍走结构相等。同步 design.md，新增 case_292~298 与跨模块扩展方法项目测试。验证：python tests/test_language_cases.py 通过 251/251；python tests/test_stdlib.py 通过 60/60；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 87 passed, 1 skipped。

- 2026-06-18: 预备修正文档与实现不和谐点：删除 design/worklog 对不存在 c-interop.md 的有效依赖，补齐位运算与复合赋值设计边界，并彻底删除 `--backend` 旧参数专门拒绝入口。why：当前能力应以已落地 case 为准，同时不保留旧兼容入口。

- 2026-06-18: 已修正文档与实现不和谐点：design.md 不再引用不存在的 c-interop.md，位运算 `& | ^ ~ << >>` 与复合赋值 `+= -= *= /= %= &= |= ^= <<= >>=` 已进入当前设计边界；nc.py 删除 `--backend` 专门拒绝逻辑，项目测试不再承诺旧参数友好诊断。验证：待本轮回归执行。

- 2026-06-18: 验证文档与实现不和谐点修正：python tests/test_language_cases.py 通过 251/251；python tests/test_stdlib.py 通过 60/60；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 86 passed, 1 skipped；python nc.py build --backend c test_cases\case_170_generics_identity.nc 现按普通路径失败为“文件不存在: --backend”。rg 仍命中 worklog 历史与本轮追加说明中的 c-interop 字符串，未回写历史条目以遵守 append-only。

- 2026-06-18: 预备删除旧边界与缓存噪音：清理仓库内 Python 缓存产物、旧语法/旧 API 专门拒绝 case、旧函数类型迁移诊断、stdlib 旧 API 黑名单文档，以及 LLVM-only 后遗留的 v1/Lite 文案。why：不向前兼容旧边界，减少 case 驱动判断中的历史噪音。

- 2026-06-18: 已删除旧边界与缓存噪音：删除 compiler/__pycache__ 缓存产物并加入忽略规则，删除旧函数类型/types.Cmp/map_has/裸 gc_collect 专门拒绝 case，移除旧函数类型迁移诊断，stdlib 文档不再列旧 API 黑名单，LLVM 后端文案去除 v1/Lite。design.md 无需更新。验证：python tests/test_language_cases.py 通过 249/249；python tests/test_stdlib.py 通过 58/58；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 86 passed, 1 skipped。

- 2026-06-18: 预备修复 Linux ncrt C 合法性问题：删除 runtime 中仅含 flexible array member 的 nc_entry 实体定义，保留头文件前向声明和 map entry 字节块 ABI。why：Ubuntu GCC 拒绝无 named member 的 flexible array struct，导致 Linux CI 在编译 ncrt 时失败；本修复不改变语言或 runtime API 边界。

- 2026-06-18: 已修复 Linux ncrt C 合法性问题：runtime 不再定义仅含 flexible array member 的 nc_entry，map entry 仍通过前向声明和字节 offset ABI 使用。design.md 无需更新。验证：gcc -c runtime/ncrt.c -o %TEMP%/ncrt-ci-fix-sentinel.o；python tests/test_language_cases.py 通过 249/249；python tests/test_stdlib.py 通过 58/58；python -m pytest tests/test_projects.py tests/test_builtin_boundary.py tests/test_llvm_backend.py tests/test_type_ref.py -q 通过 86 passed, 1 skipped。

- 2026-06-18: 预备更新 Linux CI action 版本：将 checkout/setup-python 升到当前 Node 24 action 主版本，消除 GitHub Actions Node.js 20 deprecated annotation。why：CI 已通过但仍有 runner annotation，属于维护性噪音，不改变语言或编译器行为。

- 2026-06-18: 已更新 Linux CI action 版本：actions/checkout 升至 v7，actions/setup-python 升至 v6。design.md 无需更新。验证：待 push 后 GitHub Actions Linux run 确认。

- 2026-06-18: 预备添加 README 并整理标准库文档位置：新增中文快速入口 README，将标准库 API 文档移入 docs/stdlib.md 并同步当前引用。why：仓库缺少首次打开时的项目入口，标准库文档也应和 generics/archive 等专题文档归入 docs。

- 2026-06-18: 已添加 README 并整理标准库文档位置：新增中文快速入口 README，覆盖项目定位、快速开始、CLI、回归命令、目录结构和开发规则；stdlib.md 已移至 docs/stdlib.md，并同步 design.md 与文档内部链接。语言设计边界不变。验证：python nc.py run test_cases/case_013_fun.nc；python nc.py run -c "import io fun main() { io.println(42) }"；python tests/test_language_cases.py 通过 249/249；python tests/test_stdlib.py 通过 58/58；python -m pytest tests/test_projects.py tests/test_builtin_boundary.py tests/test_llvm_backend.py tests/test_type_ref.py -q 通过 86 passed, 1 skipped。

- 2026-06-18: 预备更新 README 关键字亮点：补充 NC 关键字少的说明和完整保留词列表，并修正 README 兼容性句子。why：关键字少是当前语言表面小的直接信号，适合作为 README 的项目亮点。

- 2026-06-18: 已更新 README 关键字亮点：新增“语言表面很小”小节，列出当前 lexer 保留词，并修正“不向前兼容旧语法或旧 API”表述。design.md 无需更新。验证：README 关键字表与 compiler/lexer.py KEYWORDS 一致；python nc.py run test_cases/case_013_fun.nc 输出 42。

- 2026-06-18: 已删除旧 review 辅助服务 server.js。why：当前仓库没有使用该 Node 服务的入口或引用，只剩归档历史提及；design.md 无需更新。验证：rg -n "server\\.js|node server|npm start|http\\.createServer|require\\('http'\\)" . 仅剩 worklog 当前记录与归档历史命中。

- 2026-06-19: 预备将标准库 sort 从稳定插入排序改为不稳定 intro sort，并删除新增 sorted API 计划。why：排序默认能力应更接近标准库级复杂度保证，同时用 NC 源码验证递归、分区和堆排序实现便利性。

- 2026-06-19: 已将标准库 sort 改为不稳定 intro sort：默认排序和自定义比较排序使用三数取中快排主路径、深度耗尽堆排序兜底、小分区插入排序收尾；未新增 sorted/is_sorted API，并修复同模块私有符号访问检查以保持 sort helper 私有。同步 docs/stdlib.md，新增 sort 边界与私有 helper case。验证：python tests/test_stdlib.py 通过 60/60；python tests/test_language_cases.py 通过 249/249；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 86 passed, 1 skipped。

- 2026-06-19: 预备补齐泛型函数值与修复索引表达式解析：支持已实例化泛型函数作为 fun 值，修复 items[j - 1] 一类索引误判，并用 sort 复用 case 验证泛型与函数值闭环。why：intro sort 暴露出泛型、函数值和 parser 的组合边界尚未闭环，需要以标准库真实用法推动最小语言能力。

- 2026-06-19: 已补齐实例化泛型函数值与索引表达式解析：新增 oo[T]/module.foo[T] 函数值表达式，monomorphize 触发实例化，typecheck 生成 un(...) R 类型，LLVM 为具名函数值生成无捕获 thunk；修复 items[j - 1]/items[lo + root] 解析误判。sort.sort 已改为通过 _sort_less_ord[T] 复用 sort.by。同步 design.md 与 docs/generics.md。验证：python tests/test_stdlib.py 通过 60/60；python tests/test_language_cases.py 通过 254/254；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 88 passed, 1 skipped。

- 2026-06-19: 预备拆分 LLVM 后端 string lowering：新增可复用 CodegenContext 协议与 StringEmitter，先迁移字符串分配、转换、相等和拼接相关 lowering，LLVMCodegen 保留薄代理。why：llvm_codegen.py 已成为最大结构性热点，需要用等价重构建立后续 map/iface/function value 拆分模式。

- 2026-06-19: 已拆分 LLVM 后端 string lowering：新增 compiler/llvm_context.py 的 CodegenContext 协议与 compiler/llvm_string.py 的 StringEmitter，迁移字符串拼接、分配、[]u8/C string 转换、数值/rune/string 转换和字符串相等 lowering；LLVMCodegen 保留薄代理，行为边界不变，design.md 无需更新。验证：python -m py_compile compiler/llvm_codegen.py compiler/llvm_context.py compiler/llvm_string.py；python -m pytest tests/test_llvm_backend.py -q 通过 46 passed, 1 skipped；python tests/test_language_cases.py 通过 254/254；python tests/test_stdlib.py 通过 60/60；python -m pytest tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 42 passed。

- 2026-06-19: 预备拆分 LLVM 后端 map lowering：新增 MapEmitter 迁移 map 构造、get/set/has/delete、descriptor、hash/eq helper，LLVMCodegen 保留薄代理并复用 CodegenContext。why：string lowering 拆分模式已验证，map lowering 是下一个边界集中且收益高的后端结构热点。

- 2026-06-19: 已拆分 LLVM 后端 map lowering：新增 compiler/llvm_map.py 的 MapEmitter，迁移 map 构造、get/set/has/delete、descriptor、hash/eq helper，并扩展 CodegenContext 供后续 emitter 复用；LLVMCodegen 保留薄代理，runtime ABI 和语言行为边界不变，design.md 无需更新。验证：python -m py_compile compiler/llvm_codegen.py compiler/llvm_context.py compiler/llvm_string.py compiler/llvm_map.py；python -m pytest tests/test_llvm_backend.py -q 通过 46 passed, 1 skipped；python tests/test_language_cases.py 通过 254/254；python tests/test_stdlib.py 通过 60/60；python -m pytest tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 42 passed。

- 2026-06-19: 预备记录并实现 hosted C runtime 基线：NC v1 的 build/run 始终通过目标平台 C runtime 和默认启动环境链接，不提供 freestanding/nostd 模式；源码层 NC 标准库仍保持显式 import。why：GC、启动参数、错误输出/退出、字符串/容器 runtime 以及 fs/os/math 等能力实践依赖普通用户态 C runtime。

- 2026-06-19: 已记录并实现 hosted C runtime 基线：design.md 明确 build/run 生成 hosted 用户态程序，ncrt 构建在目标平台 C runtime 之上且 v1 不提供 freestanding/nostd；TargetSpec 新增 hosted_runtime_link_args 显式表达 gcc 默认 CRT/libc 链接基线，build_llvm_ir 每次合并 hosted 链接参数与显式 extern lib。验证：python -m py_compile compiler/target.py compiler/llvm_codegen.py；python -m pytest tests/test_llvm_backend.py -q 通过 47 passed, 1 skipped；python tests/test_language_cases.py 通过 254/254；python tests/test_stdlib.py 通过 60/60；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 89 passed, 1 skipped。

- 2026-06-19: 预备拆分 LLVM 后端类型布局：新增 LLVMLayout 承接 LLVM 类型常量、llvm_type、sizeof/align 计算和共享结构/枚举/接口布局表，LLVMCodegen 保留薄代理。why：string/map emitter 已落地，继续拆 iface/function value 前需要先收敛类型布局边界。

- 2026-06-19: 已拆分 LLVM 后端类型布局：新增 compiler/llvm_layout.py，承接 LLVM 基础/聚合类型常量、llvm_type、sizeof/align 计算以及 struct/enum/iface 共享布局表；LLVMCodegen 保留 sizeof/align 薄代理，StringEmitter 与 MapEmitter 改用统一布局常量。语言行为边界不变，design.md 无需更新。验证：python -m py_compile compiler/llvm_codegen.py compiler/llvm_context.py compiler/llvm_string.py compiler/llvm_map.py compiler/llvm_layout.py；python -m pytest tests/test_llvm_backend.py -q 通过 46 passed, 1 skipped；python tests/test_language_cases.py 通过 254/254；python tests/test_stdlib.py 通过 60/60；python -m pytest tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 42 passed。

- 2026-06-19: 预备做 basedpyright 第一轮降噪：显式声明 AST/pass 动态属性，修正少量明显可空路径，并新增保守 basedpyright 配置。why：编辑器暴露大量静态建模缺口，先把真实结构债作为雷达而非 CI 门禁处理，不改变语言行为。

- 2026-06-19: 已完成 basedpyright 第一轮降噪：新增 pyrightconfig.json，仅检查 compiler 并关闭 Unknown/Any 等当前非阻塞噪音；AST 节点显式声明 type/fallible/closure_id/_narrowed_vars/overload 等 pass 间属性，SymbolTable 初始化方法/函数表，编译管线用 _require_ast 收窄解析后 SourceFile.ast，并修复 closure_id 默认 None 后的收集哨兵。语言行为边界不变，design.md 无需更新。验证：python tests/test_language_cases.py 通过 254/254；python tests/test_stdlib.py 通过 60/60；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 89 passed, 1 skipped；npx --yes basedpyright --outputjson 从 737 errors/6198 warnings 降至 522 errors/0 warnings。

- 2026-06-19: 预备清理 LLVM 后端测试重复 case：将普通单文件 NC 程序回归收敛到 test_cases/stdlib_cases 顶层 .nc，test_llvm_backend.py 只保留 argv/env、临时文件、IR 符号、extern/link、build 产物和 target 专项等 Python 层断言。why：case 驱动测试应减少内联源码重复，保留后端测试的真实职责边界。

- 2026-06-19: 已清理 LLVM 后端测试重复 case：删除 test_llvm_backend.py 中被 base case 覆盖的普通语言/stdlib 内联程序，新增 case_304_c_keyword_identifiers.nc 与 case_282_map_growth_update.nc 承接仍有价值的普通程序覆盖；test_projects.py、test_builtin_boundary.py、test_type_ref.py 和 case_runner.py 维持现有职责。design.md 无需更新。验证：python -m pytest tests/test_llvm_backend.py -q 通过 15 passed, 1 skipped；python tests/test_language_cases.py 通过 255/255；python tests/test_stdlib.py 通过 61/61；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 57 passed, 1 skipped；rg 剩余 <memory> 内联源码均为后端/链接/环境类断言。

- 2026-06-19: 预备保留 .gitattributes 删除并拆分 LLVM 后端 function lowering：新增 FunctionEmitter 承接函数/闭包声明生成、普通/可错函数调用、函数值与闭包值 lowering，LLVMCodegen 保留薄代理。why：function value/closure 是近期泛型函数值 case 暴露出的明确边界，继续降低 llvm_codegen.py 结构热点；.gitattributes 删除为有意移除仓库级 LF 归一化策略。

- 2026-06-19: 已保留 .gitattributes 删除并拆分 LLVM 后端 function lowering：新增 compiler/llvm_function.py 的 FunctionEmitter，迁移函数/闭包声明与生成、callable body、成功/错误返回、可错函数调用、函数值/闭包值与闭包环境 lowering；LLVMCodegen 保留薄代理，语言行为边界不变，design.md 无需更新。验证：python -m py_compile compiler/llvm_codegen.py compiler/llvm_context.py compiler/llvm_function.py compiler/llvm_map.py compiler/llvm_string.py compiler/llvm_layout.py；python -m pytest tests/test_llvm_backend.py -q 通过 15 passed, 1 skipped；python tests/test_language_cases.py 通过 255/255；python tests/test_stdlib.py 通过 61/61；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 57 passed, 1 skipped；npx --yes basedpyright --outputjson 仍失败但从 522 errors/0 warnings 降至 490 errors/0 warnings。

- 2026-06-19: 预备拆分 LLVM 后端 iface lowering：新增 IfaceEmitter 承接 iface 注册、接口方法动态分派、boxing、vtable 和 thunk 生成，LLVMCodegen 保留薄代理。why：function emitter 已落地，iface thunk/vtable 是相邻且边界清楚的后端结构热点，适合继续等价重构。

- 2026-06-19: 已拆分 LLVM 后端 iface lowering：新增 compiler/llvm_iface.py 的 IfaceEmitter，迁移 iface 注册、接口方法动态分派、boxing、vtable/thunk 生成和嵌入方法解析；LLVMCodegen 保留薄代理，普通 struct 方法调用仍留在主类，语言行为边界不变，design.md 无需更新。验证：python -m py_compile compiler/llvm_codegen.py compiler/llvm_context.py compiler/llvm_iface.py compiler/llvm_function.py compiler/llvm_map.py compiler/llvm_string.py compiler/llvm_layout.py；python -m pytest tests/test_projects.py -q 通过 27 passed；python -m pytest tests/test_llvm_backend.py -q 通过 15 passed, 1 skipped；python tests/test_language_cases.py 通过 255/255；python tests/test_stdlib.py 通过 61/61；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 57 passed, 1 skipped；npx --yes basedpyright --outputjson 仍失败但从 490 errors/0 warnings 降至 468 errors/0 warnings。

- 2026-06-19: 预备拆分 LLVM 后端 method lowering：新增 MethodEmitter 承接 receiver 参数、普通/fallible struct 方法调用和窄版 operator method lowering，LLVMCodegen 保留薄代理。why：iface 已拆出，剩余方法调用语义边界清楚且有 method/fallible/operator/embed case 覆盖，适合继续等价重构。

- 2026-06-19: 已拆分 LLVM 后端 method lowering：新增 compiler/llvm_method.py 的 MethodEmitter，迁移 receiver 参数、str.c_str/map.has/iface 分流、普通 struct 方法调用、fallible method raw 调用和窄版 operator method lowering；LLVMCodegen 保留薄代理，语言行为边界不变，design.md 无需更新。验证：python -m py_compile compiler/llvm_codegen.py compiler/llvm_context.py compiler/llvm_method.py compiler/llvm_iface.py compiler/llvm_function.py compiler/llvm_map.py compiler/llvm_string.py compiler/llvm_layout.py；python tests/test_language_cases.py 通过 255/255；python -m pytest tests/test_projects.py -q 通过 27 passed；python -m pytest tests/test_llvm_backend.py -q 通过 15 passed, 1 skipped；python tests/test_stdlib.py 通过 61/61；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 57 passed, 1 skipped；npx --yes basedpyright --outputjson 仍失败但从 468 errors/0 warnings 降至 460 errors/0 warnings。

- 2026-06-19: 预备拆分 LLVM 后端 runtime support：新增 RuntimeEmitter 承接 C/ncrt runtime 符号声明、GC collect/live、malloc、错误打印/exit、全局 C 字符串和空字符串指针，LLVMCodegen 保留薄代理。why：method emitter 已落地，runtime support 边界低风险且能移除主类中的外部符号声明噪音。

- 2026-06-19: 已拆分 LLVM 后端 runtime support：新增 compiler/llvm_runtime.py 的 RuntimeEmitter，迁移 C/ncrt runtime 符号声明、GC collect/live、malloc、错误打印/exit、memcmp、全局 C 字符串和空字符串指针；LLVMCodegen 保留薄代理，并同步 builtin boundary 测试读取新文件。语言行为边界不变，design.md 无需更新。验证：python -m py_compile compiler/llvm_codegen.py compiler/llvm_context.py compiler/llvm_runtime.py compiler/llvm_method.py compiler/llvm_iface.py compiler/llvm_function.py compiler/llvm_map.py compiler/llvm_string.py compiler/llvm_layout.py；python -m pytest tests/test_llvm_backend.py tests/test_builtin_boundary.py -q 通过 18 passed, 1 skipped；python tests/test_stdlib.py 通过 61/61；python tests/test_language_cases.py 通过 255/255；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 57 passed, 1 skipped；npx --yes basedpyright --outputjson 仍失败但从 460 errors/0 warnings 降至 446 errors/0 warnings。

- 2026-06-19: 预备拆分 LLVM 后端 slice lowering：新增 SliceEmitter 承接 slice literal、array/slice/string slicing、slice value 构造、append/copy/clear 和 raw copy lowering，LLVMCodegen 保留薄代理。why：runtime/method 已拆出，slice lowering 边界有充足 case 覆盖且比控制流拆分风险更低。

- 2026-06-19: 已拆分 LLVM 后端 slice lowering：新增 compiler/llvm_slice.py 的 SliceEmitter，迁移 slice literal、array/slice/string slicing、slice value 构造、append/copy/clear 和 raw copy lowering；LLVMCodegen 保留薄代理，CodegenContext 补齐 malloc_array/map_pointer_for_expr 协议入口。语言行为边界不变，design.md 无需更新。验证：python -m py_compile compiler/llvm_codegen.py compiler/llvm_context.py compiler/llvm_slice.py compiler/llvm_runtime.py compiler/llvm_method.py compiler/llvm_iface.py compiler/llvm_function.py compiler/llvm_map.py compiler/llvm_string.py compiler/llvm_layout.py；python tests/test_language_cases.py 通过 255/255；python tests/test_stdlib.py 通过 61/61；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 57 passed, 1 skipped；npx --yes basedpyright --outputjson 仍失败但从 446 errors/0 warnings 降至 414 errors/0 warnings。

- 2026-06-19: 预备拆分 LLVM 后端 loop lowering：新增 LoopEmitter 承接条件 for、range for、slice for-in 和 map for-in，LLVMCodegen 保留薄代理。why：slice/runtime 已拆出，循环 lowering 边界集中且只依赖现有 builder/vars/break_stack 状态，适合继续等价重构。

- 2026-06-19: 已拆分 LLVM 后端 loop lowering：新增 compiler/llvm_loop.py 的 LoopEmitter，迁移条件 for、range for、slice for-in 和 map for-in；LLVMCodegen 保留薄代理，CodegenContext 显式补齐 break_stack/bool_value 协议入口。语言行为边界不变，design.md 无需更新。验证：python -m py_compile compiler/llvm_codegen.py compiler/llvm_context.py compiler/llvm_loop.py compiler/llvm_slice.py compiler/llvm_runtime.py compiler/llvm_method.py compiler/llvm_iface.py compiler/llvm_function.py compiler/llvm_map.py compiler/llvm_string.py compiler/llvm_layout.py；python tests/test_language_cases.py 通过 255/255；python tests/test_stdlib.py 通过 61/61；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 57 passed, 1 skipped；npx --yes basedpyright --outputjson 仍失败但从 414 errors/0 warnings 降至 349 errors/0 warnings。

- 2026-06-19: 预备拆分 LLVM 后端 expression control lowering：新增 ControlExprEmitter 承接 block expr、if expr、match expr、match condition 和 block tail value lowering，LLVMCodegen 保留薄代理。why：loop emitter 已落地，表达式化控制流是剩余主类热点，case 覆盖完整但比 equality 拆分更能推动结构收敛。

- 2026-06-19: 已拆分 LLVM 后端 expression control lowering：新增 compiler/llvm_control_expr.py 的 ControlExprEmitter，迁移 block expr、if expr、match expr、match condition 和 block tail value lowering；LLVMCodegen 保留薄代理，CodegenContext 补齐 emit_str_eq 协议入口。语言行为边界不变，design.md 无需更新。验证：python -m py_compile compiler/llvm_codegen.py compiler/llvm_context.py compiler/llvm_control_expr.py compiler/llvm_loop.py compiler/llvm_slice.py compiler/llvm_runtime.py compiler/llvm_method.py compiler/llvm_iface.py compiler/llvm_function.py compiler/llvm_map.py compiler/llvm_string.py compiler/llvm_layout.py；python tests/test_language_cases.py 通过 255/255；python tests/test_stdlib.py 通过 61/61；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 57 passed, 1 skipped；npx --yes basedpyright --outputjson 仍失败但从 349 errors/0 warnings 降至 326 errors/0 warnings。

- 2026-06-20: 预备完善默认参数表达式能力：明确默认值在调用端补齐且每次省略实参重新求值，补齐 slice/map/function 默认值 case，并让普通具名函数可作为无捕获函数值用于默认参数。why：默认参数已经进入语言边界，需要避免 Python 式共享可变默认值坑，并为后续 sort API 收敛打基础。

- 2026-06-20: 已完善默认参数表达式能力：design.md 明确默认值在调用端补齐并每次省略重新求值，slice literal、map 构造和函数值默认值成为正式 case；普通函数名现在可作为无捕获函数值，已实例化泛型函数值与匿名函数默认值保持可用。同步 docs/generics.md，新增 case_305~310 覆盖可变默认值 fresh 语义、具名/泛型/匿名函数值默认值和类型错误。验证：python tests/test_language_cases.py 通过 261/261；python tests/test_stdlib.py 通过 61/61；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 57 passed, 1 skipped。

- 2026-06-20: 预备让泛型默认参数表达式按调用惰性单态化，并收敛 sort API 删除 sort.by。why：默认参数已定义为调用端补齐；显式传比较器时不应提前实例化默认比较器约束，sort(items) 与 sort(items, less) 应作为同一能力闭环。

- 2026-06-20: 已实现泛型默认参数惰性单态化并收敛 sort API：monomorphize 只在调用省略默认参数时实例化默认表达式依赖，typecheck 跳过泛型实例声明阶段的默认值强制检查，默认表达式补齐保留声明处私有访问权限；sort.sort 改为单入口 `sort[T](items, less = 默认 < 比较器)`，删除公开 sort.by，显式 less 可排序非 Ord struct。同步 design.md/docs，新增 case_311 与更新 sort cases。验证：python tests/test_language_cases.py 通过 262/262；python tests/test_stdlib.py 通过 61/61；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 57 passed, 1 skipped。

- 2026-06-20: 预备添加 json 标准库模块：以动态 Value DOM 为第一版，尽量用 NC 实现 parse/stringify，并补齐 JSON 需要的递归指针形 struct LLVM 支持。why：json 是标准库核心能力，当前缺口来自真实 DOM case，不引入反射或 struct 自动映射。

- 2026-06-20: 已添加 json 标准库模块：新增动态 json.Value DOM、parse/stringify、构造/查询/数组/对象 API，json 作为保留标准模块名；LLVM struct 注册改用独立 context identified struct，支持指针/slice 形递归 struct 并拒绝直接值递归；同模块声明可引用本模块私有类型。同步 design.md/docs/stdlib.md，新增 json stdlib cases、递归 struct language cases 和 json preempt 项目测试。验证：python tests/test_language_cases.py 通过 264/264；python tests/test_stdlib.py 通过 67/67；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 58 passed, 1 skipped。

- 2026-06-21: 预备修复字段访问后索引解析：`p.s[i]`、`arr.items[i]`、`obj.entries[i]` 不应被误判为模块泛型函数值或调用，括号只能作为临时绕路，不应成为语言要求。why：字段索引是基础 postfix 链，当前 json 标准库防御式括号暴露 parser 泛型限定名分支过宽。

- 2026-06-21: 已修复字段访问后索引解析：parser 的模块泛型限定名分支现在只接受已 import 模块名前缀，普通 `p.s[i]`、`arr.items[i]`、`obj.entries[i]` 和 `lit[i]` 走正常索引后缀；新增 case_314_postfix_field_index 覆盖该组合。design.md 无需更新。验证：python tests\test_language_cases.py 通过 265/265；python tests\test_stdlib.py 单 worker 通过 67/67；python -m pytest tests\test_llvm_backend.py tests\test_type_ref.py tests\test_builtin_boundary.py tests\test_projects.py -q --basetemp=.tmp\pytest 通过 58 passed, 1 skipped。

- 2026-06-21: 预备实现统一包围逗号列表尾逗号：允许 `() / [] / {}` 包围的逗号分隔列表使用尾逗号，不改变 `for i, item in` 这类非包围语法逗号。why：多行编辑和生成代码更友好，parser 成本低且不影响 AST/typecheck/codegen 语义。

- 2026-06-21: 已实现统一包围逗号列表尾逗号：parser 新增包围逗号列表辅助逻辑，覆盖函数类型、泛型参数/实参、函数/方法参数与调用、struct/enum 声明、struct literal/new literal、数组/切片 literal，并保留空洞逗号和非包围 `for i, item in` 拒绝行为。同步 design.md，新增 case_315~318 覆盖正向与错误路径。验证：python -m py_compile compiler\parser.py；python tests\test_language_cases.py 通过 269/269；python tests\test_stdlib.py 通过 67/67；python -m pytest tests\test_llvm_backend.py tests\test_type_ref.py tests\test_builtin_boundary.py tests\test_projects.py -q 通过 58 passed, 1 skipped。

- 2026-06-21: 预备实现右侧值自足的类型省略首批能力：默认参数可由默认值推导参数类型，非空 slice literal 可写 []{...} 推元素类型；不做调用点反推、泛型实参推导、闭包参数上下文推导或 array 省略。why：默认参数和 slice literal 已有真实 case 暴露重复类型噪音，按 NC 显式可预测原则只收敛声明处自足的省略。

- 2026-06-21: 已实现右侧值自足的类型省略首批能力：默认参数支持 name = expr 从默认值推导参数类型，无默认值参数仍必须显式类型；非空 slice literal 支持 []{...} 从首元素推导元素类型，空 slice 和 array 省略仍拒绝。同步 design.md，新增 case_319~327 并更新旧未类型默认参数错误预期。验证：python -m py_compile compiler\parser.py compiler\ast.py compiler\symtab.py compiler\typecheck.py compiler\generics.py；python tests\test_language_cases.py 通过 278/278；python tests\test_stdlib.py 通过 67/67；python -m pytest tests\test_llvm_backend.py tests\test_type_ref.py tests\test_builtin_boundary.py tests\test_projects.py -q 通过 58 passed, 1 skipped。

- 2026-06-21: 预备将浮点文本互转收敛到 strconv：新增 f32/f64 对称 parse/format API，json 复用 strconv 数字解析和格式化，并清理 json 中字段索引的防御式括号。why：json 已暴露一份手写浮点解析，标准库应提供统一、严格、可替换为 Ryu/Dragonbox/fast_float 族算法的边界。

- 2026-06-21: 已将浮点文本互转收敛到 strconv：新增 parse_f32/format_f32，parse_f64 支持严格十进制 exponent，format_f32/format_f64 通过 ncrt helper 搜索可 round-trip 的短 `%g` 候选；str(f32/f64) 与 io.println(float) 复用同一格式化路径。json 现在复用 strconv.parse_f64/format_f64，并移除字段索引防御式括号；同时修复泛型 struct literal 前瞻误把 `lit[i] {` 当作类型应用的 parser 角落。同步 docs/stdlib.md，design.md 无需更新。验证：python -m py_compile compiler\parser.py compiler\llvm_codegen.py compiler\llvm_context.py compiler\llvm_runtime.py compiler\llvm_string.py；python tests\test_language_cases.py 通过 278/278；python tests\test_stdlib.py 通过 67/67；python -m pytest tests\test_llvm_backend.py tests\test_type_ref.py tests\test_builtin_boundary.py tests\test_projects.py -q 通过 58 passed, 1 skipped。

- 2026-06-21: 预备实现 NC 语义调用栈错误：将 `error` 从 str 同布局标量改为 opaque 错误对象，`err` 源头和 `??` 传播追加 NC 调用点 frame，`!!` 与 main 未捕获错误打印 message + stack。why：`!!` 报错必须直接给出调用栈，且错误栈应跨平台稳定，不依赖宿主原生 backtrace。

- 2026-06-21: 已实现 NC 语义调用栈错误：`error` LLVM/runtime 布局改为 message + frame slice 的 opaque 对象，`err` 源头、`??` 传播和 `!!` 终点追加 NC frame，`!!` 与 main 未捕获错误统一打印 `error:` + `stack:`；`error` 不再可比较或作为 map key。同步 design.md，新增/更新 err stack、method stack、stdlib stack、error 比较和 map key case；测试期望解析保留 stderr 缩进。验证：python -m py_compile compiler\parser.py compiler\ast.py compiler\symtab.py compiler\typecheck.py compiler\type_rules.py compiler\llvm_layout.py compiler\llvm_runtime.py compiler\llvm_codegen.py compiler\llvm_function.py compiler\llvm_method.py compiler\llvm_context.py tests\case_runner.py；python tests\test_language_cases.py 通过 281/281；python tests\test_stdlib.py 通过 68/68；python -m pytest tests\test_llvm_backend.py tests\test_type_ref.py tests\test_builtin_boundary.py tests\test_projects.py -q 通过 58 passed, 1 skipped。

- 2026-06-21: 预备实现源码位置魔术常量：新增 `__FILE__`、`__LINE__`、`__COL__`、`__FUNC__`，复用错误栈的源码路径和函数显示名规则。why：错误栈已证明源码位置常量有真实诊断用途，用户日志也需要同一套稳定、跨平台的源码定位能力。

- 2026-06-21: 已实现源码位置魔术常量：新增 `__FILE__ : str`、`__LINE__ : i32`、`__COL__ : i32`、`__FUNC__ : str`，作为独立 MagicConst AST 节点解析和 lowering；`__FILE__` 复用错误栈相对路径规则，`__FUNC__` 复用 NC 显示函数名并支持方法与闭包；魔术常量名不可声明或赋值。同步 design.md，新增单文件、方法、闭包、赋值拒绝、shadow 拒绝和多文件 `__FILE__` 项目测试。验证：python -m py_compile compiler\source_location.py compiler\parser.py compiler\ast.py compiler\symtab.py compiler\typecheck.py compiler\llvm_codegen.py compiler\llvm_function.py；python tests\test_language_cases.py 通过 284/284；python tests\test_stdlib.py 通过 68/68；python -m pytest tests\test_llvm_backend.py tests\test_type_ref.py tests\test_builtin_boundary.py tests\test_projects.py -q 通过 59 passed, 1 skipped。

- 2026-06-21: 预备收敛大写绑定、模块魔术常量和内存源码路径：全大写 `let` 绑定作为不可重赋值绑定，新增 `__MODULE__` 返回目录模块名，并把 `<memory>` 从普通 case 可见期望收缩为无路径源码 fallback。why：常量约定、模块诊断和测试路径都应贴近当前目录模块模型，同时不引入 comptime 或深度不可变。

- 2026-06-21: 已收敛大写绑定、模块魔术常量和内存源码路径：`let FOO` 等 ASCII 全大写绑定不可重赋值但仍允许运行期 initializer；新增 `__MODULE__ : str` 并保留魔术常量 reserved/shadow/assignment 规则；case runner 传真实 case 文件路径，源码路径输出统一为 `/`，`<memory>` 仅作为无路径源码 fallback。同步 design.md，新增 case_334~340、模块项目测试和空路径 fallback 测试。验证：python -m py_compile compiler\source.py compiler\source_location.py compiler\parser.py compiler\symtab.py compiler\typecheck.py compiler\llvm_codegen.py tests\case_runner.py tests\test_projects.py tests\test_llvm_backend.py；python tests\test_language_cases.py 通过 291/291；python tests\test_stdlib.py 通过 68/68；python -m pytest tests\test_llvm_backend.py tests\test_type_ref.py tests\test_builtin_boundary.py tests\test_projects.py -q 通过 61 passed, 1 skipped。

- 2026-06-23: 预备收窄默认参数表达式边界：默认值从普通表达式收敛为无调用的值构造表达式，禁止普通函数调用、方法调用和可错操作，但保留 literal、前序参数引用、struct/slice/map 构造、函数值和显式类型转换。why：P2 暴露默认值、调用点补齐、泛型惰性实例化和可错 ABI 叠加后复杂度过宽；按 case 驱动保留已证明有用的默认值能力。

- 2026-06-23: 已收窄默认参数表达式边界：design.md 删除“普通表达式”默认值边界，默认参数现在拒绝普通函数调用、方法调用和 `??`/`!!`/`is err` 可错操作；保留 slice/map/struct 构造、具名/泛型/匿名函数值和显式类型转换。新增 case_342~347 覆盖直接调用、方法调用、三种可错操作和嵌套调用拒绝，并更新 case_320/323。验证：python -B -m py_compile compiler\typecheck.py；python tests\test_language_cases.py 通过 298/298；python tests\test_stdlib.py 通过 68/68；python -m pytest tests\test_llvm_backend.py tests\test_type_ref.py tests\test_builtin_boundary.py tests\test_projects.py -q 通过 61 passed, 1 skipped。

- 2026-06-23: 预备将 map 构造从 `map[K,V]()` 迁移为字面量 `map[K,V]{...}` / `map[K,V]{}`，并删除旧 `()` 构造边界。why：map 是容器值，字面量能表达初始化内容；项目不向前兼容旧语法，旧空构造不应保留为例外。

- 2026-06-23: 已将 map 构造迁移为字面量：新增 MapLiteral AST/parser/typecheck/LLVM lowering，支持 `map[K,V]{key: value, ...}` 与 `map[K,V]{}`，重复 key 按从左到右插入由后者覆盖；删除 `map[K,V]()` builtin 构造入口并迁移现有 cases/default 参数用例。同步 design.md/docs/stdlib.md，新增 case_290~294 覆盖正向、类型错误、非法类型参数和旧构造删除。验证：python -B -m py_compile compiler\parser.py compiler\ast.py compiler\typecheck.py compiler\llvm_codegen.py compiler\llvm_map.py compiler\builtins.py compiler\symtab.py compiler\generics.py compiler\__init__.py；python tests\test_language_cases.py 通过 298/298；python tests\test_stdlib.py 通过 73/73；python -m pytest tests\test_llvm_backend.py tests\test_type_ref.py tests\test_builtin_boundary.py tests\test_projects.py -q 通过 61 passed, 1 skipped。

- 2026-06-23: 预备实现简单推断全局原则与 map 省略 literal：将默认参数、非空 slice literal 和非递归函数返回类型推断收敛为“声明本体内可简单推断则可省略类型声明”，并新增非空 `map{key: value}` 从首个 key/value 推导 `map[K,V]`。why：现有规则已分散证明该方向可用，需要统一设计边界，同时减少 map literal 的重复类型噪音。

- 2026-06-23: 已实现简单推断全局原则与 map 省略 literal：design.md 新增声明本体内简单推断原则，明确 literal 默认类型、非递归函数返回推断和不做目标/调用点/泛型/后续使用反推；parser/typecheck 支持非空 `map{key: value}` 从首个 key/value 推导 `map[K,V]`，空 `map{}` 仍拒绝并要求 `map[K,V]{}`。新增 case_348~353 覆盖正向、类型不一致、空 map 和目标类型不反推。验证：python -B -m py_compile compiler\parser.py compiler\ast.py compiler\typecheck.py compiler\llvm_codegen.py compiler\llvm_map.py compiler\builtins.py compiler\symtab.py compiler\generics.py compiler\__init__.py；python tests/test_language_cases.py 通过 304/304；python tests/test_stdlib.py 通过 73/73；python -m pytest tests/test_llvm_backend.py tests/test_type_ref.py tests/test_builtin_boundary.py tests/test_projects.py -q 通过 61 passed, 1 skipped。

- 2026-06-23: 预备清理 struct 运算符协议：新增 __neg__ 一元特殊方法，改 types.Ord 为数值类型或具备 __lt__ 的 struct，并让 <=/>/>= 在缺少手写方法时由 __lt__ 派生。why：当前 struct 比较重载与泛型 Ord 脱节，且缺少 unary negation case；按已决策的最小核心 ordering 收敛协议。

- 2026-06-23: 已清理 struct 运算符协议：新增 `__neg__` 一元特殊方法；`types.Ord` 现在接受数值类型或具备合法 `__lt__` 的 struct；`<=`、`>`、`>=` 优先使用手写 `__le__`/`__gt__`/`__ge__`，否则由 `__lt__` 派生，只有 `__le__` 不会反推 `>`。同步 design.md/docs，新增 case_354~360 与 sort 默认 struct Ord case。验证：python -B -m py_compile compiler\ast.py compiler\constraints.py compiler\type_rules.py compiler\typecheck.py compiler\llvm_method.py compiler\llvm_codegen.py；python tests\test_language_cases.py 通过 311/311；python tests\test_stdlib.py 通过 74/74；python -m pytest tests\test_llvm_backend.py tests\test_type_ref.py tests\test_builtin_boundary.py tests\test_projects.py -q 通过 61 passed, 1 skipped。

- 2026-06-23: 预备将 `is err` 替换为 `try` 错误处理语句。why：`is` 只服务单一布尔错误测试，不值得占用关键字；`try` 能同时表达可错调用、成功值作用域和错误对象作用域，且不引入公开 Result 类型。

- 2026-06-23: 已将 `is err` 替换为 `try` 错误处理语句：lexer 删除 `is` 关键字并新增 `try`，parser/typecheck/LLVM 后端支持 `try value = call() { ... } else e { ... }` 与 void call 形态，省略 else 时按 `!!` 打印错误栈退出；成功值和错误对象限定在各自块作用域，旧 `call() is err` 改为拒绝 case，README 前置错误处理章节并同步 design.md。验证：python -B -m py_compile compiler\lexer.py compiler\parser.py compiler\ast.py compiler\symtab.py compiler\typecheck.py compiler\llvm_codegen.py compiler\llvm_function.py；python tests\test_language_cases.py 通过 319/319；python tests\test_stdlib.py 通过 74/74；python -m pytest tests\test_projects.py tests\test_builtin_boundary.py tests\test_llvm_backend.py tests\test_type_ref.py -q 通过 61 passed, 1 skipped。

- 2026-06-23: 预备实现 `match error` 并强化 README 错误处理发布叙事：允许 `try else e` 中用 `match e { "message" -> ...; else -> ... }` 按错误 message 完整字符串相等分类，不开放 error inspect/wrap/code/tag。why：当前 `??`/`!!`/`try` 已解决显式传播和局部分支，但 Go 式错误处理的主要诟病还包括错误分类样板代码；先用 case 驱动补齐最小可发布能力。

- 2026-06-23: 已实现 `match error`：typecheck 允许 `error` scrutinee 使用字符串字面量 pattern 并要求 `else`，LLVM lowering 提取 error message 后复用字符串相等；`error` 仍不可比较、不可作为 map key，也不开放 inspect/wrap/code/tag。README 已强化错误处理前置叙事，design.md 同步当前边界。新增 case_369~374 覆盖命中、else、str 结果、非法 pattern、缺少 else、重复 pattern 和比较防漏。验证：python -B -m py_compile compiler\typecheck.py compiler\llvm_control_expr.py compiler\llvm_codegen.py；python tests\test_language_cases.py 通过 325/325；python tests\test_stdlib.py 通过 74/74；python -m pytest tests\test_projects.py tests\test_builtin_boundary.py tests\test_llvm_backend.py tests\test_type_ref.py -q 通过 61 passed, 1 skipped。

- 2026-06-23: 预备补齐 `str: types.Ord`：允许 `str < <= > >= str` 使用 UTF-8 原始字节序，并让 `sort.sort[str]` 默认排序可用。why：`str` 已是 Eq/Hash/Zero 且常用于 map key 与排序数据，Ord 缺口现在阻碍默认排序闭环；不引入 Unicode collation、locale 或自然排序。

- 2026-06-23: 已补齐 `str: types.Ord`：typecheck 允许同类型 `str` 大小比较，`types.Ord` 接受 `str`，LLVM/runtime 新增 `__nc_str_cmp_ptr` 按 UTF-8 原始字节序比较；`sort.sort[str]` 默认排序可用，旧 str Ord 拒绝 case 改为正向并新增 case_375 覆盖比较、前缀、空串和非 ASCII 字节序。同步 design.md/docs。验证：python -B -m py_compile compiler\typecheck.py compiler\type_rules.py compiler\llvm_codegen.py compiler\llvm_string.py compiler\llvm_runtime.py；python tests\test_language_cases.py 通过 326/326；python tests\test_stdlib.py 通过 74/74；python -m pytest tests\test_projects.py tests\test_builtin_boundary.py tests\test_llvm_backend.py tests\test_type_ref.py -q 通过 61 passed, 1 skipped。

- 2026-06-24: 预备改造错误处理语法：新增内部 never 分支合并，添加 `err?` / `match?` 后缀错误处理表达式，并允许函数/函数类型使用可选 `err` 标注。why：当前 `try` 会把 happy path 嵌套到最深层，`??` 又只能原样传播，缺少同一平面上的自定义错误处理与错误分类。

- 2026-06-24: 已改造错误处理语法：新增内部 `__never` 分支合并，`ret`/`err` 可直接出现在 if/match 表达式胳膊中；新增 `call() err? e { ... }` fallback/传播后缀和 `call() match? e { ... }` 错误 message 分类后缀；函数/方法声明支持返回类型后 `err` 显式断言，函数类型可解析 `fun(T) R err` 但可错函数值仍按 v1 边界拒绝。同步 README/design，新增 case_376~389 覆盖正向和错误路径。验证：python tests\test_language_cases.py 通过 340/340；python tests\test_stdlib.py 通过 74/74；python -m pytest tests\test_llvm_backend.py tests\test_type_ref.py tests\test_builtin_boundary.py tests\test_projects.py -q 通过 61 passed, 1 skipped。

- 2026-06-24: 预备推进 TypeRef 结构化重构：parser/AST/typechecker/符号表和表达式类型改用结构化 TypeRef，类型身份暂以内部规范格式化串为 key，后端热点支持 TypeRef、其余路径通过统一格式化桥接，并将用户诊断中的函数类型显示为 `fun(T) R err`。why：类型字符串已同时承担语法、语义、ABI 查询和诊断职责，继续扩展函数类型与错误边界会放大手切字符串风险。

- 2026-06-24: 已推进 TypeRef 结构化重构：parser 类型语法直接产出 TypeRef，别名展开、模块限定、泛型替换和 typecheck/符号表可承载结构化类型；TypeRef 保留内部规范串 key 并新增用户格式化，函数类型诊断显示 `fun(T) R err`；LLVM layout/iface 等热点支持 TypeRef，遗留后端路径经统一格式化兼容。新增嵌套函数类型诊断 case 并更新函数类型错误期望。验证：python -B -m py_compile compiler\type_ref.py compiler\parser.py compiler\ast.py compiler\symtab.py compiler\typecheck.py compiler\type_rules.py compiler\builtins.py compiler\generics.py compiler\__init__.py compiler\source.py compiler\llvm_layout.py compiler\llvm_codegen.py compiler\llvm_iface.py；python tests\test_language_cases.py 通过 341/341；python tests\test_stdlib.py 通过 74/74；python -m pytest tests\test_llvm_backend.py tests\test_type_ref.py tests\test_builtin_boundary.py tests\test_projects.py -q 通过 62 passed, 1 skipped。

- 2026-06-24: 预备规整内部 ABI、模块对象和增量依赖图：新增内部 ABI 章程，统一符号命名入口，添加 build --keep-objs debug manifest，并把 build 产物从全程序单对象推进到可观察的模块对象骨架。why：link 阶段需要透明，后续增量编译需要明确模块节点、符号和泛型实例需求边界。

- 2026-06-24: 已规整内部 ABI 与模块对象 debug 构建：新增统一 ABI 符号 helper，非 extern NC 函数/方法/闭包/thunk/map/iface 生成符号采用可读骨架 + 短 hash；build --keep-objs 生成每模块 NC obj/ll、abi-manifest.json、链接输入清单和按模块 IR 指纹的对象缓存，stdlib C support 仍单独对象；design.md 同步内部 ABI、模块对象、泛型实例归定义模块和 manifest/cache 边界。验证：python tests\\test_language_cases.py 通过 341/341；python tests\\test_stdlib.py 通过 74/74；python -m pytest tests\\test_llvm_backend.py tests\\test_type_ref.py tests\\test_builtin_boundary.py tests\\test_projects.py -q 通过 64 passed, 1 skipped。

- 2026-06-24: ABI 保留前缀检查补强：用户顶层符号从拒绝 __nc_ 收紧为拒绝 __nc*，与内部 ABI 章程一致。验证：python -B -m py_compile compiler\\symtab.py；python -m pytest tests\\test_llvm_backend.py tests\\test_type_ref.py tests\\test_builtin_boundary.py tests\\test_projects.py -q 通过 64 passed, 1 skipped。
