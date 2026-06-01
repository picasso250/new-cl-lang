# worklog

## 2026-05-31

- 预备实现标准库 `strings` v1：新增内置一级模块，提供无分配字节级 contains/starts_with/ends_with/index；同步 runtime helper、LLVM lowering、case、设计文档与边界测试。
- 已实现标准库 `strings` v1：`strings` 加入内置模块集合并优先于同级目录；新增 contains/starts_with/ends_with/index 的 str 参数类型检查、ncrt 字节级 helper 与 LLVM lowering，空子串规则按设计落地。新增 case_245~247 覆盖正向、类型错误和未 import 错误，项目级测试覆盖同级 strings/ 被内置模块抢占。验证通过：`python tests/test_basic.py`；`python -m pytest tests/test_projects.py tests/test_builtin_boundary.py tests/test_llvm_backend.py tests/test_type_ref.py -q`。

- 预备清理 C 后端遗留的 `codegen_collect.py`：删除未使用收集，把 LLVM 所需的顶层分类和 closure 发现内移到 `llvm_codegen.py`。
- 已清理 C 后端遗留的 `codegen_collect.py`：删除独立收集器，LLVM 后端内部完成顶层分类与 closure 发现；移除未使用的 slice/function type/link lib 收集，link libs 继续由 compiler API 从顶层 extern block 收集。验证通过：`python tests/test_basic.py`；`python -m pytest tests/test_projects.py tests/test_builtin_boundary.py tests/test_llvm_backend.py tests/test_type_ref.py -q`。
- 预备清理 `names.py` 的 C 保留字遗留：LLVM-only 后端不再避让 C keyword，只保留用户名与 `__nc_` runtime/internal 前缀冲突的防线；同步把符号表中的 C runtime 命名改为 NC/runtime 命名。
- 已清理 `names.py` 的 C 保留字遗留：删除 `RESERVED_NAMES`，`safe_user_ident()` 仅处理 `__nc_` 前缀冲突；`symtab.py` 中的 C runtime 命名改为 runtime 命名，extern 仍可声明 runtime/libc 符号。新增 LLVM 测试覆盖 `auto`/`register`/`restrict` 可作为普通变量名。验证通过：`python -m pytest tests/test_llvm_backend.py -q`；`python tests/test_basic.py`；`python -m pytest tests/test_projects.py tests/test_builtin_boundary.py tests/test_llvm_backend.py tests/test_type_ref.py -q`。

- 预备实现 `size_of(T)` 语言级编译期内建：只接受类型实参，类型检查验证可见且可确定 ABI size，LLVM 降为 `u64` 常量，并把后端现有大小计算统一改为 ABI 对齐布局。
- 已实现 `size_of(T)`：新增 AST 节点和类型语法解析，类型检查递归验证 sized/可见类型并返回 `u64`，LLVM 降为常量；后端大小计算改为 ABI 对齐，复用于 struct/slice/array/closure env 分配与复制。新增 case_227~230 和跨模块私有类型测试。验证通过：`python tests/test_basic.py`；`python -m pytest tests/test_projects.py tests/test_builtin_boundary.py tests/test_llvm_backend.py tests/test_type_ref.py -q`。

- 预备重做 extern lib 路径功能：从 `a92070c` 干净基线重新实现 `extern { ... }` 默认链接与 `extern "path.lib" { ... }` 链接输入收集；不保留 `extern "c"` 语义。
- 已重做 extern lib 路径功能：`ExternBlock.source` 改为 `lib`，parser 支持无字符串 extern 与可选链接输入字符串，typecheck 仅校验 extern 函数 ABI；新增 `compile_nc_sources_with_libs()` 供 run/build 传递链接库，`compile` 仍只输出 LLVM IR。迁移 case_189/191/193~196 到 `extern { ... }`，删除旧 source 错误 case，并补真实 `.lib` 链接测试与 compile-only link libs 收集断言。验证通过：`python tests/test_basic.py`、`python -m pytest tests/test_projects.py tests/test_builtin_boundary.py tests/test_llvm_backend.py tests/test_llvm_cases.py tests/test_type_ref.py -q`、`python nc.py build test_cases\case_189_extern_c_putchar.nc` 后运行 `build\main.exe` 输出 `A`、`python nc.py compile -c "extern { fun putchar(c: i32): i32 } fun main() {}"`。

- 预备实验 `test_basic` 并发化：按 CPU 数量决定 worker，先以当前串行约 26s 为基线，若并发中位数至少减少 30% 则保留并提交，否则回退实现改动。
- 已保留 `test_basic` 并发化：默认 worker 为 `min(32, os.cpu_count() or 1)`，可通过 `NC_TEST_BASIC_WORKERS=1` 强制串行；修复 ncrt 缓存 miss 时多进程写同一临时 obj 的竞态。串行基线 25.85s，并发实测 11.98s/41.81s/12.05s，中位数约 12.05s，减少约 53%；验证通过 `python tests/test_basic.py`、设置 `NC_TEST_BASIC_WORKERS=1` 后的 `python tests/test_basic.py`、`python -m pytest tests/test_basic.py -q` 与核心 pytest 组合回归。
- 预备质疑并收敛 comptime 设计：删除通用 `comptime fun` / `comptime if` 的 v1 承诺，改为冻结该能力；后续只在具体 case 推动下考虑窄化的常量表达式、`static_assert` 或 `cfg`。
- 已收敛 design.md 的 comptime 章节：v1 明确不引入通用 `comptime`，并记录后续只按具体 case 考虑常量表达式、`static_assert`、`cfg`、`size_of(T)` 等窄化能力。
- 预备实现标准库 v1 第一刀：新增内置一级模块 `fs`，把裸 `read_file` / `write_file` 迁移为 `fs.read_file` / `fs.write_file`，不保留向前兼容；`len` / `append` / 类型转换继续作为语言内建。
- 已实现标准库 v1 第一刀：`fs` 加入内置模块集合，`fs.read_file` / `fs.write_file` 替代裸文件 IO；ncrt 增加带状态返回的私有文件 IO helper，LLVM 层读写失败设置现有异常 flag 并可被 `try/catch` 捕获。
- 已迁移文件 IO case 和 LLVM 测试，补裸 `read_file` / `write_file` 删除、未 import `fs`、内置 `fs` 抢占同级目录、读失败 throw 覆盖；验证通过 `python tests/test_basic.py` 与 pytest 组合回归。

## 当前状态快照 (2026-05-25)

- import/module namespace 已落地为 import v1：同级目录一级模块、命名空间限定访问、导入图递归加载、重复加载去重、cycle 报错、跨模块 `_` 顶层私有。
- 标准输出已从裸 `print(...)` 迁移到内置一级模块 `io`：需 `import io` 后调用 `io.println(value)`；裸 `print(...)` 不再识别为 builtin。
- `io` 是保留标准模块名：`import io` 不查找同级 `io/` 目录，不参与 import cycle，且优先于真实同级 `io/`。
- 早期 worklog 中“显式 import/module namespace 尚未落地”“print 仍是 builtin/magic boundary”等记录是历史状态，不代表当前缺口。
- 仍未解决的结构性债：C 复合字面量仍偏位置式、defer/throw/return 与未来自动 GC root 生命周期仍需系统处理、代码生成仍未拆分为多文件输出。

## 2026-05-16

- 项目初始化。代号：NC（New C）。
- 确定早期方向：编译到 C + 运行时库、Go 级性能、GC、comptime、胖指针泛型。
- 建立 design.md、review.html、server.js；反馈原文移入 `processed/`。
- 语言早期决策：
  - `fun` 作为函数关键字；`let` / `let mut` 区分不可变与可变。
  - 目录即模块；模块名由目录推断；显式 import/module namespace 尚未落地。
  - 默认私有，`pub` 公开，大小写与可见性无关。
  - 异常模型：`throw` 不标注异常类型；引入 `defer`。
  - 并发暂降为库级决策；无 `go` / `channel` / `select` 关键字。
  - 单返回值；无多返回值。
  - 指针只保留 `*T`，不做 `*const T`。
  - `str = {u8*; u64}`，`[]T = {T*; u64; u64}`。
  - 行注释使用 `#`。
- 编译器起步：Python 实现，BDD 驱动，C 后端。
- case_001~020：完成 print、算术、let/mut、if/for/fun/return、str、struct、逻辑运算、enum、switch、定长数组。
- `已处理/` → `processed/`
- 后续删除 `while` 关键字，条件循环统一写作 `for condition { ... }`。

---

## 20-case 自省 (2026-05-16)

- 已形成 lexer / parser / ast / symtab / typecheck / codegen / runtime 的多 pass 雏形。
- 递归下降优先级链已成型；Pass1 收集类型与函数签名，Pass2 做类型检查和局部变量。
- 20-case 时未就的 `enum`、`switch`、`[]T`、`str` 真布局、文件 IO、for-in 后续已基本落地，不再作为当前缺口。
- 当前更高风险差距：**显式 import/module namespace、标准库边界、defer/throw/return 与 GC root 生命周期、代码生成拆分**。
- 仍需处理的设计债：
  - `print` 仍是 builtin/magic boundary，尚未标准库化。
  - C 复合字面量仍偏位置式，如 `Point{3,4}`，不是字段名式。
  - 复合赋值、更多数值类型、指针语义系统压测仍未完成。

---

## 2026-05-17 运行时债

- if-expression lowering 会生成临时变量。若临时变量类型是 `str`、`[]T`、`nc_map`、`*Struct` 等持有 GC 堆指针的类型，目前不会被自动加入 GC root。
- 当前手动 GC 下通常不炸；但若未来 GC 在分配时自动触发，或表达式求值期间出现 `gc_collect()`，临时值可能被过早回收。
- 这不是泄露问题，而是 premature free / dangling pointer 风险。自动 GC 前必须处理。

---

## 2026-05-19

- case_090~094：补 defer / root 生命周期 / 错误定位保守组。
  - `defer` 延迟到函数退出执行。
  - 多个 `defer` 按 LIFO 执行。
  - `return` / `throw` 路径会先执行已登记 defer。
  - `defer`、`break` 补 span，类型错误和非法 break 能定位到源码行列。
- 激进第一刀：编译输入从单 source 升级为 source set。
  - 新增 `compile_nc_sources_to_c([(filename, source), ...])`。
  - 同目录多 `.nc` 文件合并为一个 module，Pass1/Pass2/codegen 共用原流水线。
  - `nc.py run <dir>`、`nc.py compile <dir>` 支持目录。
  - `nc.py build <file|dir>` 输出 `build/main.c` 与 `build/main.exe`。
  - 新增项目级 fixture：多文件函数调用、多文件 struct 使用、build 输出检查。
  - 多文件诊断已升级为源文件路径 + 行列，如 `file.nc:2:3: ...`。

### 当前边界

- 多文件现在是“同目录自动互见”，还不是 import/module namespace。

---

## 2026-05-20

- 循环关键字收敛：删除 `while`，条件循环统一为 `for condition { ... }`。
- `defer` 从函数级静态登记改为运行时登记栈：
  - 只有实际执行到的 `defer` 会登记。
  - 循环中每次执行到 `defer` 都会登记一次。
  - 函数退出、return、throw 路径按登记栈 LIFO 执行。
- 预备更新 `design.md` 中已过期的控制流与 block 表达式描述，使其和当前实现一致；随后评估是否把 `if` 统一为表达式节点。

- 预备实施 if 统一表达式化：删除语句/表达式双节点语义，支持无 else 的 void if，保持 else-if 为同类型表达式链。

## 2026-05-21

- 设计 `match` 语句。
- 决策：`switch` 不保留，用 `match` 统一替代。
- `match` 是表达式（支持 `let x = match y { ... }`）。
- v1 范围：字面量 + enum 标签 + `else` 分支；暂不引入通配符 `_`、guard、范围和多模式。
- `match` 编译为 if-else 链，不落入 C switch。

## 2026-05-21

- 预备新增 `match` 表达式 v1：支持字面量 / enum 标签 / else 分支，要求表达式分支类型一致。
- v1 暂不做 enum payload 解构、变量绑定、guard、范围模式；enum 无 else 时做穷尽性检查，非 enum 必须写 else。
- 已实现 `match` 表达式：lexer/parser/AST/typecheck/codegen 全链路接入，降到 `if/else if/else` 链并保证 scrutinee 只求值一次。
- 新增 case_124~134 覆盖 enum 穷尽、else、str scrutinee、tail return、block arm、函数参数和主要错误诊断；`python tests/test_basic.py` 通过 132/132，`python tests/test_projects.py` 通过。
- 应要求彻底移除语言级 `switch`：删除 Switch AST、switch token/关键字、parser 入口、Pass1/Pass2/codegen 分支；旧 switch case 改为 match，break 错误文案改为仅 loop。
- 清理后 `python tests/test_basic.py` 通过 132/132，`python tests/test_projects.py` 通过。

## 2026-05-25

- 预备清理旧 `switch` 残留：旧 case 文件名改为 `match` 语义，并补一个 `switch` 已移除的语法错误 case，避免后续误读为仍支持旧语法。
- 修正方向：`switch` 不应作为保留关键字报错；既然语言级 `switch` 已移除，就退回普通标识符。新增 case 覆盖 `let switch = 7`。
- 预备收紧指针边界：禁止 `*T` 参与算术、索引和大小比较；同类型指针仅允许 `==` / `!=`，避免 NC 指针退化成 C 指针运算。

## 2026-05-25

- 预备实施 nil 语义重构：`*T` 改为非空指针，新增 `?*T` nullable pointer；`nil` 仅允许用于 nullable pointer，并支持 `if p != nil` 块内轻量收窄。

- 已实施 nil 语义重构：lexer/parser 支持 `nil` 与 `?*T`，typecheck 支持 nullable pointer 赋值兼容、nil 比较、非空收窄和收窄块内禁止重赋值，codegen 将 `nil` 降为 `NULL` 且 `?*T` 沿用指针布局。新增 case_140~146 覆盖正向与错误路径；`python tests/test_basic.py` 通过 144/144。

- 预备落地全基础数值类型：支持 `i8/i16/i32/i64/u8/u16/u32/u64/f32/f64`、整数/浮点字面量后缀、显式数值转换，并禁止算术、比较、赋值、传参、返回、容器元素中的隐式数值提升。

- 已落地全基础数值类型：lexer/parser 支持整数与浮点后缀，typecheck 将默认整数定为 `i32`、默认浮点定为 `f64`，算术/比较/赋值/传参/返回/struct/array/slice 均要求数值类型完全一致，所有基础数值类型支持显式转换，C 后端补齐类型映射、浮点字面量和 print 输出。新增 case_147~153 覆盖正向与错误路径；`python tests/test_basic.py` 通过 151/151，`python tests/test_projects.py` 通过。

## 2026-05-25

- 预备实现 import v1：一级同级目录模块、命名空间限定访问、导入模块独立顶层命名空间、下划线顶层私有；保持同目录 .nc 自动互见。
- 已实现 import v1：lexer/parser 支持顶层 `import foo`，项目加载器按入口目录父级递归加载同级模块并检测 missing/empty/cycle，合并前将非入口模块顶层符号降为 `module.symbol` 命名空间。
- 已接通限定函数调用、类型标注、struct literal / `new`、enum variant，C 后端将限定名降为下划线 C 符号；跨模块 `_` 顶层符号禁止访问。
- 新增项目级测试覆盖函数、跨模块多文件、struct、enum、同名符号隔离、私有符号、missing/empty/cycle、非顶层 import 与不支持语法；`python tests/test_basic.py` 通过 151/151，`python -m pytest tests/test_projects.py -q` 通过 11/11。`python tests/test_projects.py` 按计划运行成功但该脚本本身无输出。


## 2026-05-25

- 预备迁移标准输出到内置一级模块 io：import io + io.println(value)；不保留裸 print(...) 兼容，并批量迁移现有 case 与项目测试。

- 已迁移标准输出边界：io 作为内置一级标准模块，import io 不查找同级目录且优先于真实 io/；io.println(value) 识别为唯一输出 builtin，裸 print(...) 不再识别。
- 已批量迁移现有 case 和项目测试到 import io + io.println(...)，并补覆盖无 io/ 目录、同级 io/ 冲突、裸 print 失败、未 import io 失败；python tests/test_basic.py 通过 151/151，python -m pytest tests/test_projects.py tests/test_builtin_boundary.py -q 通过 17/17。

## 2026-05-25

- 预备整理文档当前状态：不改历史记录，只追加当前状态快照，标明 import/module namespace 与标准输出边界已落地，避免早期 worklog 债项误导后续工作。

## 2026-05-25

- 预备拆分 compiler/codegen.py：先只抽离 codegen 前置收集阶段，保持 C 输出行为不变，避免一次性重构整个 codegen pass。

- 已抽离 codegen 前置收集阶段到 compiler/codegen_collect.py：顶层定义、闭包、slice 类型、函数值类型统一由 collect_codegen_inputs() 产出；compiler/codegen.py 从 947 行降到 706 行，C 输出行为不变。
- 验证通过：python tests/test_basic.py 通过 151/151，python -m pytest tests/test_projects.py tests/test_builtin_boundary.py -q 通过 17/17。

## 2026-05-26

- 预备继续拆分 compiler/codegen.py：抽离 codegen 运行上下文中低风险的临时变量编号、表达式缩进和 GC root 追踪辅助，保持 C 输出行为不变。

- 已抽离 codegen 运行上下文到 compiler/codegen_context.py：集中管理临时变量编号、表达式生成缩进、函数级 GC root 追踪和 root push 规则；compiler/codegen.py 从 706 行降到 659 行，C 输出行为不变。
- 验证通过：python tests/test_basic.py 通过 151/151，python -m pytest tests/test_projects.py tests/test_builtin_boundary.py -q 通过 17/17。

## 2026-05-26

- 预备实施 GC 正确性补强 v1：修复显式 gc_collect 模型下参数/聚合字段/slice 重赋值/return 与 throw defer 路径/root 与 gray 容量/GC 管理内存 free 等误回收和 UB 风险；不引入后台线程、自动触发或并行 GC。

- 已实施 GC 正确性补强 v1：runtime root 改为动态 root slot 表，gray 栈动态扩容，GC 分配/root/gray 扩容失败 abort；codegen 对参数、receiver、closure env/参数、返回槽、catch/throw 值、局部变量以及 struct/[N]T 聚合内 GC 引用递归建立 root slot；slice/str/map/pointer/function env 重赋值通过槽读取最新值，不再重复 push 旧值。
- 已移除 map rehash/free 对 GC 管理 entries 的直接 free，旧 entries 交由 GC 回收。新增 case_154~163 覆盖参数临时值、slice 重赋值、struct 字段、数组元素、return/throw defer、map rehash、字段/数组赋值和 root/gray 扩容。
- 验证通过：python tests/test_basic.py；python -m pytest tests/test_projects.py tests/test_builtin_boundary.py -q。

## 2026-05-26

- 预备新增并行 LLVM Lite 后端 v1：CLI 增加 --backend c|llvm，默认 C 不变；LLVM 先打通基础类型、函数、return、let/assign、if/for condition、算术比较和 io.println，生成 build/main.ll、build/main.obj、build/main.exe。


- 已新增并行 LLVM Lite 后端 v1：compiler/llvm_codegen.py 复用现有 parse/symtab/typecheck 后生成 LLVM IR，支持基础数值/bool、字面量、算术比较、let/assign、函数/return、if、条件 for、函数调用和 io.println。
- CLI 已接入 --backend c|llvm，默认 c 不变；compile --backend llvm 输出 LLVM IR，build --backend llvm 输出 build/main.ll、build/main.obj、build/main.exe，run --backend llvm 可直接执行。
- LLVM object 生成使用 llvmlite 0.47，注册 all targets/asmprinters，固定 MinGW GNU triple x86_64-w64-windows-gnu 与 reloc=static，避免 MSVC triple 下 MinGW 链接 __chkstk 问题。
- 新增 tests/test_llvm_backend.py 覆盖空 main、println/control-flow/function call、IR/object/exe 产物。验证通过：python tests/test_basic.py；python -m pytest tests/test_projects.py tests/test_builtin_boundary.py tests/test_llvm_backend.py -q。


## 2026-05-26

- 预备按目标调整路线：文档改为目标 LLVM、C 暂为全集/权威后端；本轮扩 LLVM 覆盖到 str 字面量与 io.println(str)，为后续 runtime C ABI/GC/slice 迁移铺路。


- 已调整设计定位：LLVM 是目标默认后端，C 当前仍是全集/权威回归后端；记录了 LLVM 切默认门槛和放弃/延期能力必须写文档的规则。
- 已扩 LLVM 覆盖率：新增 str LLVM 布局、字符串字面量、io.println(str)、len(str)、str ==/!=（memcmp）、基础数值显式转换。新增 tests/test_llvm_backend.py 覆盖字符串输出、长度/相等和 numeric casts。
- 验证通过：python tests/test_basic.py；python -m pytest tests/test_projects.py tests/test_builtin_boundary.py tests/test_llvm_backend.py -q。


## 2026-05-26

- 预备扩 LLVM 覆盖到定长数组基础能力：支持 [N]T 类型、数组字面量、索引读取，目标覆盖 case_020_array 的核心路径；本轮不做 slice、for-in 或索引赋值。


- 已扩 LLVM 覆盖率到定长数组基础能力：支持 [N]T 类型、数组字面量（含非常量元素）、索引读取和索引赋值；test_cases/case_020_array.nc 已可用 --backend llvm 运行。
- 新增 LLVM 测试覆盖数组字面量/索引和索引赋值。


## 2026-05-26

- 预备扩 LLVM 覆盖到 struct 值类型基础能力：支持 struct 声明布局、字段名顺序初始化、字段读取和字段赋值，目标覆盖 case_016_struct 和字段赋值基础路径；本轮不做 new 指针/方法/GC root。


- 已扩 LLVM 覆盖率到 struct 值类型基础能力：支持 struct 声明布局、按字段名顺序初始化、字段读取、字段赋值、struct 参数/返回；同时补非 void 函数尾表达式返回。
- 当前仍未做 struct 指针/new、方法、GC root 聚合保活；这些不是本轮放弃点，而是后续迁移项。已验证 --backend llvm 可运行 case_016_struct、case_056_struct_literal_order、case_074_field_assign、case_079_struct_param_return。


## 2026-05-26

- 预备扩 LLVM 覆盖到 enum 与 match 表达式基础能力：enum 降为 i32 tag，支持 Enum::Variant、enum 比较，以及整数/字符串/bool/enum match arms 与 else；目标覆盖 case_018_enum、case_019_match_enum、case_124_match_enum_expr、case_125_match_else_str。


- 已扩 LLVM 覆盖率到 enum 与 match 表达式基础能力：enum 降为 i32 tag，支持 Enum::Variant、enum 比较，以及整数/字符串/bool/enum match 表达式与 else 分支。
- 新增 LLVM 测试覆盖 enum + match、match else 返回 str；已验证 --backend llvm 可运行 case_018_enum、case_019_match_enum、case_124_match_enum_expr、case_125_match_else_str。


## 2026-05-26

- 预备扩 LLVM 覆盖到 block 表达式与 match/block/tail 组合：支持 { statements; tail_expr } 作为普通表达式、函数参数和 match arm body，并验证 match 尾表达式返回路径。


- 已扩 LLVM 覆盖率到 block 表达式与 match/block/tail 组合：支持 BlockExpr 作为 let initializer、函数参数和 match arm body；block 内变量表恢复，避免污染外层符号。
- 已验证 --backend llvm 可运行 case_084_block_expr_let、case_085_block_expr_call_arg、case_126_match_tail_return、case_127_match_block_arm。


## 2026-05-26

- 预备扩 LLVM 覆盖到 range for：实现 ForIn(start/end) 即 or i in start..end，循环变量为 i32；本轮不做 slice/array for-in。


- 已扩 LLVM 覆盖率到 range for：支持 or i in start..end，循环变量为 i32，按 start <= i < end 递增；slice/array for-in 仍留给后续 slice/runtime 迁移。
- 新增 LLVM 测试覆盖 range for 累加；已验证 --backend llvm 可运行 case_036_for_range。


## 2026-05-26

- 预备扩 LLVM 覆盖到 slice 基础能力：先支持 []T 布局、slice literal、len(slice)、slice index，以及 [N]T[lo:hi] 复制成 slice；底层暂用 libc malloc，不接 GC root/append。


- 已扩 LLVM 覆盖率到 slice 基础能力：支持 []T 布局、slice literal、len(slice)、slice index、[N]T[lo:hi] 复制成 slice、slice 参数/返回和 or i, item in s。底层暂用 libc malloc，append/GC root/重分配留后续 runtime 迁移。
- 新增 LLVM 测试覆盖 slice literal/len/index/参数返回、数组切片复制和 slice for-in；已验证 --backend llvm 可运行 case_021_slice、case_026_forin、case_038_slice_lit。


## 2026-05-26

- 已扩 LLVM 覆盖率到 slice append：支持 append([]T, T)，包括 []i32 与 []str；append 当前总是 malloc 新底层并复制旧元素，不复用 cap，不接 GC allocator/root。
- 已补 slice 的 slice[lo:hi] 复制路径，新增 LLVM 测试覆盖 append、slice re-slice alias、[]str append；已验证 --backend llvm 可运行 case_025_append、case_039_slice_str_append、case_040_append_alias、case_080_slice_param_return。


## 2026-05-26

- 预备扩 LLVM 覆盖到字符串索引/切片/拼接：实现 str[index] -> i32 byte、str[lo:hi] 复制、str + str 复制拼接，继续使用 libc malloc 暂不接 GC allocator。


## 2026-05-26

- 已扩 LLVM 覆盖率到字符串索引/切片/拼接：支持 str[index] 返回 i32 byte、str[lo:hi] 复制、str + str 复制拼接；构造的新字符串暂用 libc malloc，不接 GC allocator/root。
- 新增 LLVM 测试覆盖字符串索引、切片、拼接；已验证 --backend llvm 可运行 case_022_str、case_024_streq、case_027_str_slice、case_028_str_cat。


## 2026-05-26

- 预备扩 LLVM 覆盖到 break：维护 loop end block 栈，支持 break 跳出条件 for、range for 和 slice for-in；同时让已终止 block 不再继续发射后续语句。


- 已扩 LLVM 覆盖率到 break：支持在条件 for、range for、slice for-in 中 break 到当前 loop end block；block 已终止后不再发射后续语句。
- 新增 LLVM 测试覆盖三类 loop 中的 break；已验证 --backend llvm 可运行 case_037_len_break。


## 2026-05-26

- 预备扩 LLVM 覆盖到临时文件 IO builtins：支持 read_file(path) 与 write_file(path, content)，直接调用 MinGW libc fopen/fread/fwrite/fclose，打开失败保持 C 后端当前空串/忽略写入语义；本轮仍不接 NC GC allocator/root。


- 已扩 LLVM 覆盖率到临时文件 IO builtins：read_file/write_file 直接声明并调用 MinGW libc fopen/fread/fwrite/fclose/fseek/ftell；打开失败返回空 str，写入打开失败直接忽略。读入 buffer 当前仍用 libc malloc，不接 NC GC allocator/root。


## 2026-05-26

- 预备扩 LLVM 覆盖到 nc_map 基础能力：支持 map_new、m[str]=str、m[str]、map_has、len(map)。本轮 LLVM map 使用连续 entry + 线性查找 + 满容量复制增长，先保证语言语义，不复刻 C runtime 哈希表内部布局；底层仍暂用 libc malloc，不接 GC root。


- 已扩 LLVM 覆盖率到 nc_map 基础能力：支持 map_new、字符串键索引赋值/读取、map_set_s/map_get_s、map_has、len(map)，并覆盖容量增长与覆盖更新。LLVM map 当前使用连续 entry + 线性查找 + malloc 复制增长，未复用 C runtime 哈希表，也未接 GC root。


## 2026-05-26

- 预备扩 LLVM 覆盖到临时转换 builtins：支持 str(i32) 通过 sprintf 生成字符串，支持 i32(str) 通过 atoi 解析；本轮继续使用 libc malloc，先覆盖 case_031_cast 与字符串拼接组合。


- 已扩 LLVM 覆盖率到临时转换 builtins：str(i32) 使用 sprintf 写入 malloc buffer，i32(str) 使用 atoi 读取字符串指针；已覆盖 case_031_cast 与 i32(str) 基础路径。


## 2026-05-26

- 预备扩 LLVM 覆盖到临时 GC 测试钩子：gc_collect() 暂实现为 no-op，gc_live() 输出并返回 0，用于覆盖当前不释放内存的 LLVM malloc 路径。此实现不是默认 LLVM 达标所需的真正 GC root/allocator。


- 已扩 LLVM 覆盖到临时 GC 测试钩子：gc_collect() no-op，gc_live() 输出/返回 0。放弃点/延期点：本轮未实现真正 GC registry、root slot、释放与扫描；默认 LLVM 达标前必须补 runtime allocator/root 或明确替代方案。


## 2026-05-26

- 预备扩 LLVM 覆盖到 struct 指针与方法基础能力：支持 new Struct 分配、*Struct 字段读取、指针 receiver 方法声明与 obj.method() 调用；先覆盖 case_033_method，分配仍使用 libc malloc，不接 GC allocator/root。


- 已扩 LLVM 覆盖到 struct 指针与方法基础能力：支持 new Struct、*Struct 字段读取、指针 receiver 方法声明和 obj.method(args) 调用，已覆盖 case_033_method。分配仍用 libc malloc，未接 GC allocator/root。


## 2026-05-26

- 放弃点/延期点：LLVM 本轮不实现 throw/try/catch/defer。原因是正确语义需要跨函数 unwinding、异常 frame 栈、setjmp/longjmp ABI 与 defer 栈统一运行时；在 runtime C object/ABI 边界落地前，半套实现会偏离 C 后端语义。后续继续推进非异常能力，默认 LLVM 达标前必须回补该项或重新设计异常 runtime。


## 2026-05-26

- 预备扩 LLVM 覆盖到无捕获 closure/function value：使用 {call, env} fat pointer，call 签名首参为 i8* env；本轮仅支持 captures 为空的 FunctionExpr 与 closure 调用，捕获 env 继续延期。


- 已扩 LLVM 覆盖到无捕获 closure/function value：FunctionExpr 生成 __nc_lambda_N，值布局为 {call, env}，closure 调用传入 env + 参数；已覆盖 case_099_closure_no_capture。捕获 closure/env struct/GC root 仍延期。


## 2026-05-26

- 预备扩 LLVM 覆盖到 nullable pointer 基础能力：支持 nil 字面量、?*T 初始化、p != nil / nil != p 比较，以及窄化块内字段/方法访问；先覆盖 case_140_nullable_nil 和 case_141_nullable_method。


- 已扩 LLVM 覆盖到 nullable pointer 基础能力：支持 nil 字面量、?*T 初始化、nil 比较以及 typecheck 窄化后的字段/方法访问；已验证 case_140_nullable_nil、case_141_nullable_method。


## 2026-05-26

- 预备补 LLVM 项目级回归：把多文件同模块、跨模块 import、跨模块 struct/enum、同名 public 符号隔离纳入 --backend llvm pytest，锁住默认后端达标门槛中的项目级证据。


- 已补 LLVM 项目级回归：多文件同模块 fixture、跨模块函数 import、跨模块 struct/enum、同名 public 符号隔离均纳入 --backend llvm pytest；现有项目级 LLVM 正向路径已锁定。


## 2026-05-28

- 预备扩 LLVM 覆盖到捕获 closure：复用 {call, env} fat pointer，为每个 FunctionExpr 生成 env struct，创建 closure 时 malloc env 并按值拷贝 captures，lambda 入口从 env 字段读取捕获变量；本轮仍不接 GC root。


- 已扩 LLVM 覆盖到捕获 closure/function value：支持 env struct、按值拷贝 captures、closure 参数传递、closure 返回、i32/str/slice 捕获；已验证 case_100~105、case_113、case_114。延期点：closure env 仍使用 libc malloc，尚未纳入 GC root/allocator。


## 2026-05-28

- 预备补 LLVM 单文件正向 case 自动回归：从 test_cases 读取 # STDOUT 期望，使用 --backend llvm 跑所有非异常/defer 延期 case，作为切默认前的持续门槛。


- 已补 LLVM 单文件正向 case 自动回归：tests/test_llvm_cases.py 读取 # STDOUT 并跑所有非异常/defer 延期 case；同时修正 LLVM io.println(bool) 为 1/0、浮点输出为 %g 风格，与 C 后端/test_cases 期望对齐。


## 2026-05-28

- 预备补 LLVM 错误 case 自动回归：读取 test_cases 中 # ERROR 期望，用 python nc.py compile --backend llvm 验证必须失败且诊断包含期望文本，补齐默认后端达标门槛中的错误用例证据。


- 已补 LLVM 错误 case 自动回归：tests/test_llvm_cases.py 现在同时覆盖 # STDOUT 正向 case 和 # ERROR 编译错误 case；LLVM compile --backend llvm 对所有错误 case 均验证失败诊断包含期望文本。


## 2026-05-28

- 预备收敛 LLVM runtime 分配路径：新增 __nc_gc_alloc shim，所有 LLVM 后端动态分配从 libc malloc 改为该入口；gc_live 返回当前分配计数，gc_collect 暂不释放但清零计数。此轮目标是 runtime ABI 收敛，不是完整 GC。


- 已收敛 LLVM runtime 分配路径：slice、map、closure env、heap struct、字符串构造与 read_file buffer 均走 __nc_gc_alloc shim；gc_live 现在输出该入口的分配计数，gc_collect 暂不释放对象但清零计数。延期点：仍未实现 root slot、扫描和释放。


## 2026-05-28

- 预备扩 LLVM 覆盖到轻量 throw/try/catch：使用全局异常 flag + str value，在函数边界返回默认值传播异常，try 块在语句后检查 flag 并跳 catch；本轮不实现 defer，也不使用 setjmp/longjmp。


- 已扩 LLVM 覆盖到轻量 throw/try/catch：全局异常 flag + str value，函数返回默认值传播，try 语句边界跳 catch，uncaught throw 在 main 输出 stderr 并返回 1；已验证 case_035_throw、case_043_uncaught_throw。defer 仍延期。


## 2026-05-28

- 预备扩 LLVM 覆盖到 defer：为每个函数维护 i32 defer site 栈与 top，defer 语句动态 push site id；函数 fallthrough、显式 return、throw 传播前按 LIFO 执行已注册 defer。先覆盖 case_090~092、case_097~098 及 GC+defer 组合。


- 已扩 LLVM 覆盖到 defer：函数内维护动态 defer site 栈，按 LIFO 在 fallthrough、return、throw 前执行；已验证 case_090~092、case_097~098、case_158、case_159，并将 LLVM 正向 case gate 取消 defer 跳过。


## 2026-05-28

- 预备将 CLI 默认后端切换到 LLVM：nc.py run/compile/build 无 --backend 时走 LLVM；C 后端保留为 --backend c。同步更新 build 测试，确保默认 build 产出 main.ll/main.obj/main.exe，C build 仍显式可用。


- 已将 CLI 默认后端切换到 LLVM：run/compile/build 无 --backend 时走 LLVM，默认 build 产出 main.ll/main.obj/main.exe；C 后端保留为 --backend c，C build 测试改为显式 --backend c。已验证默认 run/compile/build smoke、C 后端回归和 LLVM pytest。


## 2026-05-28

- 预备明确 LLVM v1 默认后端的 GC 边界和放弃点：当前默认后端采用不释放的 __nc_gc_alloc shim 保证对象保活，真正 root slot 注册、heap 扫描、释放/复用和 runtime GC ABI 延期到默认切换后的 runtime 工作。


- 已明确 LLVM v1 默认后端的 GC 边界和放弃点：design.md 记录默认 LLVM 采用不释放的 __nc_gc_alloc shim 保证动态分配对象保活，真正 root slot、heap 扫描、释放/复用和 runtime GC ABI 延期；已验证 C/reference 回归与 LLVM 全量 case/project pytest。


## 2026-05-29

- 预备提取独立 ncrt 静态运行时：新增 runtime/ncrt.h + runtime/ncrt.c 并编译为 ncrt.obj，C/LLVM 后端共享链接该对象；LLVM 保持当前不释放 GC 边界，gc_collect 只清零 live counter。

- 已提取独立 ncrt 静态运行时：新增 runtime/ncrt.h + runtime/ncrt.c，run/build 路径按需编译 ncrt.obj；C 后端输出改为 include ncrt.h 并链接 ncrt.obj，不再内联共享 runtime。
- LLVM 后端删除内部 __nc_gc_alloc/live counter 实现，改为声明外部 ncrt 函数并链接 ncrt.obj；str cat/slice/eq、str(i32)、i32(str)、read_file/write_file、map_new/get/set/has 均通过 ncrt ABI。Windows aggregate ABI 下 LLVM 使用指针式 ncrt 包装函数，避免 str 按值跨 C 边界不匹配。
- LLVM nc_map 布局已改为匹配 ncrt.h 的 entries/cap/len/tombstones，entries 在 LLVM 侧 opaque，len(map) 读取 len 字段；C runtime 哈希表成为唯一 map 实现。
- 验证通过：python tests/test_basic.py；python -m pytest tests/test_projects.py tests/test_builtin_boundary.py -q；python -m pytest tests/test_llvm_backend.py tests/test_llvm_cases.py -q；默认 LLVM build 与 --backend c build smoke 均产出 ncrt.obj 并可运行。未迁移项：按元素类型生成的 slice append/copy helper 仍保留在 C 生成代码中。

## 2026-05-29

- 预备将 slice append/copy 迁入 ncrt：保持 `[]T = { ptr, len, cap }` 三字段布局不变，新增字节级 raw slice helper，C 后端只生成 typed wrapper，LLVM 后端调用同一组 ncrt helper，统一两后端 slice 复制/增长语义。

- 已将 slice append/copy 迁入 ncrt：新增 `nc_slice_raw`、`__nc_slice_copy_raw`、`__nc_slice_append_raw`；C 后端 typed slice helper 只做 raw ABI wrapper，LLVM 后端的 slice copy/append 改为调用同一组 ncrt helper。`elem_size` 保持为调用点常量参数，不进入 slice header。
- 验证通过：python -m pytest tests/test_llvm_backend.py -q；python tests/test_basic.py；python -m pytest tests/test_projects.py tests/test_builtin_boundary.py tests/test_llvm_cases.py -q。


## 2026-05-29

- 预备补齐运算符实现：新增位运算、复合赋值和语句级自增/自减，按 Go 风格优先级接入 lexer/parser/typecheck/C 后端/LLVM 后端，并补正向与错误 case。

- 已补齐运算符实现：lexer/parser 支持位运算、复合赋值和语句级 ++/--；typecheck 收紧整数位运算、复合赋值与自增自减 lvalue 规则；C/LLVM 后端均支持对应 lowering。新增 case_164~169 覆盖正向优先级/复合赋值/++-- 与错误路径。
- 验证通过：python tests/test_basic.py；python -m pytest tests/test_projects.py tests/test_builtin_boundary.py -q；python -m pytest tests/test_llvm_backend.py tests/test_llvm_cases.py -q；默认 LLVM run/build smoke 与 --backend c build smoke 均通过。

## 2026-05-29

- 预备优化测试套件耗时：为共享 ncrt.obj 增加内容哈希缓存，减少重复 runtime 编译；LLVM 单文件 case 改为进程内调用编译/运行入口，避免每个 case 启动 Python CLI 子进程。


- 已优化测试套件耗时：build_ncrt_obj 现在基于 runtime/ncrt.c 与 runtime/ncrt.h 内容哈希复用缓存对象，并仍复制到目标 out_dir/ncrt.obj；LLVM 单文件 case 测试改为进程内调用 compile_nc_sources_to_llvm_ir + run_llvm_ir，保留 CLI smoke 覆盖在既有项目/后端测试中。
- 验证通过：python tests/test_basic.py；python -m pytest tests/test_projects.py tests/test_builtin_boundary.py -q；python -m pytest tests/test_llvm_backend.py tests/test_llvm_cases.py -q；组合 pytest --durations=20 为 58 passed in 64.85s，最慢项 test_basic 28.55s、LLVM 正向 case 22.10s。

## 2026-05-29

- 预备实现 LLVM 真实 GC 与 C 端对齐：将共享 ncrt 从不释放 stub 升级为显式 mark-sweep；LLVM 后端按 C 后端 root slot 规则注册参数、局部、返回槽、异常值、closure env 与聚合内部 GC 指针字段；更新测试和设计文档以移除旧 LLVM GC 延期边界。

- 已实现共享 ncrt 显式 mark-sweep GC：`__nc_gc_alloc` 记录 block header/size/mark/link 并清零 payload；`gc_collect` 从 root slot 表标记可达块，保守扫描已标记 heap payload 内 machine word，sweep 未标记块；`gc_live` 返回当前存活 block 数；root slot 表动态扩容并支持 mark/rewind/drop/pop。
- LLVM 后端已接入 root frame：main 入口初始化 GC，函数/closure 入口 root mark，参数、receiver、closure env、局部变量、返回槽、catch error 和 throw 临时按类型递归注册 root，所有 return/异常传播出口 rewind；heap struct 分配改为 `__nc_gc_alloc`。
- 已更新 LLVM GC hook 测试期望，并新增 helper 局部对象离开函数后可回收的 LLVM 覆盖。已验证：python -m pytest tests/test_llvm_backend.py tests/test_llvm_cases.py -q；python tests/test_basic.py；python -m pytest tests/test_projects.py tests/test_builtin_boundary.py -q；python nc.py build test_cases\case_032_gc.nc；python nc.py build --backend c test_cases\case_032_gc.nc。


## 2026-05-29

- 预备实现 Go 风格显式泛型 v1：支持 fun/struct 类型参数、显式类型实参调用与类型应用，通过 frontend monomorphization 在 symtab/typecheck 前生成普通声明；v1 仅支持 any 约束，不做类型推断和独立泛型方法。

- 已实现显式泛型 v1：parser/AST 支持 fun/struct 类型参数、显式类型实参调用和类型应用；新增 frontend monomorphization pass，在 symtab/typecheck 前将用到的泛型函数/struct 实例化为普通声明，后端继续只接收具体 AST。
- 已补正向与错误 case，覆盖 identity、generic struct/new、slice/pointer 字段、嵌套实例、跨模块泛型、缺失/错误类型实参、未知类型参数、实例化后类型不匹配和非泛型误用；design.md 已记录 v1 语法与限制。
- 验证通过：python tests/test_basic.py；python -m pytest tests/test_projects.py tests/test_builtin_boundary.py -q；python -m pytest tests/test_llvm_backend.py tests/test_llvm_cases.py -q；python nc.py build test_cases\case_170_generics_identity.nc；python nc.py build --backend c test_cases\case_170_generics_identity.nc。

## 2026-05-29

- 预备删除 C 后端：移除 NC→C 代码生成实现、--backend c|llvm 双入口和旧 C API；CLI 固定使用 LLVM，runtime/ncrt.c 作为 LLVM 链接运行时保留。


- 已删除 C 后端：移除 compiler/codegen.py、compiler/codegen_context.py、compiler/runtime.py 和 compiler/c_abi.py；CLI run/compile/build 固定走 LLVM，显式 --backend 报错；compiler API 只保留 LLVM IR/run/build 路径。
- 已将 builtin boundary 收敛为类型推断，命名清洗迁到 backend-neutral names helper；runtime/ncrt.c 与 ncrt.h 继续作为 LLVM 链接运行时保留。
- 已更新 tests/test_basic.py 改用 LLVM IR 跑全部 case，项目/builtin 测试移除 C 输出断言并新增 --backend 删除断言；design.md 已更新为 LLVM-only 当前边界。
- 验证通过：python tests/test_basic.py；python -m pytest tests/test_projects.py tests/test_builtin_boundary.py -q；python -m pytest tests/test_llvm_backend.py tests/test_llvm_cases.py -q；python nc.py build test_cases\case_170_generics_identity.nc；python nc.py build --backend c test_cases\case_170_generics_identity.nc 按预期失败。

## 2026-05-29

- 预备实现类型别名 v1：支持 `type Name = Type` 语法，在 parse_module_sources 阶段展开别名（替换为底层类型字符串），对后续所有 pass 透明。
- 仅限同模块内使用，不跨模块。

## 2026-05-29

- 合并 C 互操作设计：`runtime` 内置库 + `extern` 声明两条路径，写入 c-interop.md。删除 ffi-design.md 与 runtime-module-design.md。

## 2026-05-29

- 已实现类型别名 v1：
  - lexer 新增 `type` 关键字
  - ast 新增 TypeAlias 节点
  - parser 新增 `type Name = Type` 语法和 `_parse_type_alias`
  - `__init__.py` 新增 `_expand_type_aliases_in_module`，在 parse_module_sources 中收集别名并展开
  - 别名展开支持：简单名、指针/切片/数组/函数类型/泛型应用中的递归替换
  - 循环别名检测（展开前验证所有别名无循环）
  - 重复别名检测
  - 新增 case_181~186 覆盖基本/函数/struct/切片/循环错误/重复错误
- 验证通过：python tests/test_basic.py（184/184）；python -m pytest tests/test_llvm_backend.py tests/test_builtin_boundary.py tests/test_projects.py tests/test_llvm_cases.py -q（57/57）。

## 2026-05-29

- 预备实现 runtime 内置模块与 extern "c" v1：runtime 只公开 gc_collect/gc_live，删除裸 GC builtin；新增最小 C ABI extern 函数声明、类型限制、LLVM declare 与正反向测试。

- 已实现 runtime 内置模块与 extern "c" v1：`runtime` 加入内置模块集合，`runtime.gc_collect()` / `runtime.gc_live()` 替代裸 GC builtin；裸 `gc_collect()` / `gc_live()` 已删除并由错误 case 覆盖。
- 已实现顶层 `extern "c" { fun name(params): Ret }` 解析、extern 函数符号注册、C ABI scalar/pointer 类型限制、LLVM `declare` 与普通调用 lowering；v1 明确不支持其他来源字符串、函数体、varargs、泛型 extern、`str`/聚合/NC runtime 类型。
- 已更新 design.md 与 c-interop.md，使 `runtime` 公开面、`ncrt` 私有 ABI 和 extern v1 边界与实现一致。新增 case_187~196 与项目级 runtime 内置模块优先级测试。
- 验证通过：python tests/test_basic.py；python -m pytest tests/test_projects.py tests/test_builtin_boundary.py -q；python -m pytest tests/test_llvm_backend.py tests/test_llvm_cases.py -q；python nc.py build test_cases\case_189_extern_c_putchar.nc 并运行 build\main.exe 输出 A。

## 2026-05-30

- 预备统一函数类型标注语法：从旧 `(T) -> R` 改为 `fun(T) R`，内部类型字符串继续使用 `fn(T)->R`；不保留旧语法兼容，并迁移 closure/function type 相关 case 与文档。
- 已统一函数类型标注语法：parser 类型位置改为解析 `fun(T) R` 并继续生成内部 `fn(T)->R`；旧 `(T) -> R` 语法明确报错。已迁移 closure/function type/type alias 相关 case 与 LLVM 内联测试，并更新 design.md/todo.md。
- 验证通过：python tests/test_basic.py；python -m pytest tests/test_llvm_backend.py tests/test_llvm_cases.py tests/test_projects.py tests/test_builtin_boundary.py -q。

## 2026-05-30

- 预备实现 iface v1：顶层 iface 声明、接口嵌入、指针 receiver 方法自动满足接口、接口值赋值/传参/返回与动态方法调用；v1 不做值 receiver、接口到接口重装箱、泛型接口或显式 implements。

- 已实现 iface v1：lexer/parser/AST 支持顶层 iface、方法签名和接口嵌入；symtab/typecheck 支持接口全局类型、嵌入 method set 扁平化、未知/循环/冲突检测、指针 receiver 方法自动满足接口、接口值赋值/传参/返回和接口方法调用检查。
- LLVM 后端已支持接口胖指针 { i8* vtable, i8* data }、按 *T -> I 转换生成 vtable 全局常量与 erased receiver thunk、接口动态分派，并将 GC root 限定到 data 字段。新增 case_197~208 和项目级跨模块/private iface 覆盖。
- v1 边界已写入 design.md：仅支持 un (p *T) method(...) 自动满足；不支持值 receiver、接口到接口重装箱、泛型接口、显式 implements、类型断言或接口 nil。
- 验证通过：python tests/test_basic.py；python -m pytest tests/test_llvm_backend.py tests/test_llvm_cases.py tests/test_projects.py tests/test_builtin_boundary.py -q；python nc.py build test_cases\case_197_iface_basic.nc 并运行 build\main.exe 输出 42。

## 2026-05-30

- 预备清理 import 绕路与类型字符串遗留：parser 直接识别已导入/内置模块限定函数调用，删除 _rewrite_import_calls；新增集中 TypeRef 解析/格式化入口并替换主要手写解析；将条件循环 AST/后端命名从 While 收敛为 ForCondition。


- 已清理 import 绕路与类型字符串遗留：parser 基于模块 import 集合直接生成限定 FunctionCall，删除 _rewrite_import_calls；新增 compiler/type_ref.py 作为类型字符串解析/格式化入口，并替换别名展开、模块名限定、泛型替换、函数/slice/array 类型解析；str 不再作为符号表伪 struct 注册；条件循环 AST/LLVM block 命名从 While 收敛为 ForCondition。
- 验证通过：python tests/test_basic.py；python -m pytest tests/test_projects.py tests/test_builtin_boundary.py tests/test_llvm_backend.py tests/test_llvm_cases.py tests/test_type_ref.py -q；python nc.py build test_cases\case_197_iface_basic.nc 并运行 build\main.exe 输出 42。

## 2026-05-30

- 预备实现 rune 与字符串插值 v1：新增独立 rune 字面量/类型/显式转换/输出语义，并将 `"Hello, {expr}"` 在前端表达为插值字符串，类型检查后由 LLVM 后端降为 `str(...)` 与字符串拼接。
- 已实现 rune 与字符串插值 v1：新增 RuneLiteral/InterpolatedString，字符字面量支持 `\u{...}` 码点转义并拒绝空/多码点/非法码点；`rune` 类型独立于 numeric，仅允许同类型 `==`/`!=`，支持 `str(rune)`、`rune(i32/u32)`、`i32/u32(rune)` 与 `io.println(rune)` UTF-8 输出。
- 字符串插值支持任意表达式、嵌套括号/字符串/字符扫描、`{{`/`}}` 字面量大括号，并在类型检查阶段限制为可 stringify 类型；LLVM 后端降为 `str(...)` 与 `__nc_str_cat_out` 左结合拼接。`str[index] -> i32` 字节索引语义保持不变。
- 新增 case_209~215 覆盖 rune 正向、插值正向、rune 类型错误、非法字符字面量、rune 运算错误、空插值和不可 stringify 插值。验证通过：python tests/test_basic.py；python -m pytest tests/test_projects.py tests/test_builtin_boundary.py tests/test_llvm_backend.py tests/test_llvm_cases.py tests/test_type_ref.py -q；python nc.py build test_cases\case_210_string_interpolation.nc 并运行 build\main.exe；python nc.py build test_cases\case_209_rune_basic.nc 并确认输出含 UTF-8 bytes e4b8ad。


## 2026-05-31

- 预备实现内建泛型 map[K,V] v1：删除旧 map_new/nc_map 用户边界，支持 map[K,V]() 构造、标量 K/V、索引读写/复合赋值、map_has 与 len(map)，并把 ncrt map helper 改为 tagged scalar nc_val。

- 已实现内建泛型 map[K,V] v1：map[K,V]() 走内建构造，K/V 限定为基础标量；索引读写、复合赋值、map_has 与 len(map) 按静态 K/V 检查，旧 map_new 用户边界已删除。ncrt map ABI 改为 tagged scalar nc_val，LLVM 负责标量装箱/拆箱，缺失 key 返回 V 零值。新增 case_216~225 覆盖标量正向、缺失零值、复合赋值和错误路径；design.md 已同步。验证通过：python tests/test_basic.py；python -m pytest tests/test_projects.py tests/test_builtin_boundary.py tests/test_llvm_backend.py tests/test_llvm_cases.py tests/test_type_ref.py -q；python nc.py build test_cases\\case_216_map_generic_scalars.nc 并运行 build\\main.exe。

## 2026-05-31

- 预备补标准库输出能力：新增 `io.print(value)`，参考 Go `fmt.Print` / Python `print(..., end="")`，与 `io.println` 支持同一组可输出类型，但不追加换行；同步补 case、文档与边界测试。
- 已补标准库输出能力：新增 `io.print(value)`，复用 `io.println` 的输出类型集合与 LLVM lowering，仅不追加换行；新增 case_226 覆盖 str/rune/bool/int 混合连续输出，并更新 design.md 与 builtin 边界测试。验证通过：python tests/test_basic.py；python -m pytest tests/test_projects.py tests/test_builtin_boundary.py tests/test_llvm_backend.py tests/test_llvm_cases.py tests/test_type_ref.py -q。

## 2026-05-31

- 预备删除重复的 LLVM 单文件 case 回归：`tests/test_llvm_cases.py` 已被 LLVM-only 的 `tests/test_basic.py` 覆盖，保留 `test_basic` 作为 `test_cases` 权威门槛。

- 已删除重复的 `tests/test_llvm_cases.py`：LLVM-only 后 `tests/test_basic.py` 已覆盖同一批 `test_cases` 正向/错误回归且支持 extern 链接库。验证通过：`python tests/test_basic.py`；`python -m pytest tests/test_projects.py tests/test_builtin_boundary.py tests/test_llvm_backend.py tests/test_type_ref.py -q`。

- 预备实现第一批基础内建：新增 cap/copy/delete/clear/min/max/abs，覆盖 slice 容量与复制、map 删除/清空以及数值常用函数；同步补 case、design 和 builtin 边界测试。

- 已实现第一批基础内建：cap(s)、copy(dst, src)、clear(slice/map)、delete(map, key)、min/max 与 bs；ncrt 增加 slice copy/clear 与 map delete/clear helper，LLVM lowering 和类型检查已接入。新增 case_231~236 覆盖正向和错误路径，design.md 与 builtin 边界测试已同步。验证通过：python tests/test_basic.py；python -m pytest tests/test_projects.py tests/test_builtin_boundary.py tests/test_llvm_backend.py tests/test_type_ref.py -q。

- 预备扩展标准库 fs 基础路径操作：新增 `fs.exists`、`fs.remove`、`fs.rename`、`fs.mkdir`，延续当前内置标准模块边界与 throw 失败语义；`exists` 对不存在返回 false。
- 已扩展标准库 fs 基础路径操作：新增 `fs.exists`、`fs.remove`、`fs.rename`、`fs.mkdir`，ncrt 提供平台封装；`remove` 支持文件与空目录，`rename` 在目标已存在时失败，其他失败通过现有异常路径 throw。新增 case_237~241 覆盖路径操作、类型错误和 throw 捕获；更新 design.md 与 builtin/project 边界测试。验证通过：python tests/test_basic.py；python -m pytest tests/test_projects.py tests/test_builtin_boundary.py tests/test_llvm_backend.py tests/test_type_ref.py -q。

- 预备实现标准库 `os` 模块 v1：新增内置一级模块 `os`，提供 args/getenv/has_env/cwd/exit；LLVM main 改为接收 argc/argv 并保存供 `os.args()` 使用，runtime/ncrt 增加私有 OS helper；同步补 case、设计文档与边界测试。
- 已实现标准库 `os` 模块 v1：`os` 加入内置模块集合并优先于同级目录；新增 `os.args`/`os.getenv`/`os.has_env`/`os.cwd`/`os.exit` 类型检查、LLVM lowering 和 ncrt 私有 helper；LLVM `main` 改为 C ABI `main(i32 argc, i8** argv)` 并保存 argc/argv。新增 case_242~244 与项目/LLVM 边界测试，`run_llvm_ir` 支持传入 args/env。验证通过：`python tests/test_basic.py`；`python -m pytest tests/test_projects.py tests/test_builtin_boundary.py tests/test_llvm_backend.py tests/test_type_ref.py -q`。

- 预备拆分标准库/内置函数边界文档与测试目录：新增 stdlib.md，design.md 只保留索引；将标准库/语言级 builtin 专项 case 迁到 stdlib_cases/；抽共享 case runner 并拆分 language/std lib 测试入口。

- 已拆分标准库/内置函数边界文档与测试目录：新增 stdlib.md 记录 io/fs/os/runtime/strings 与语言级 builtin 边界；design.md 改为索引引用；抽 tests/case_runner.py，共享 # STDOUT/# STDERR/# RC/# ERROR 解析、并发和单文件运行逻辑；新增 tests/test_language_cases.py 与 tests/test_stdlib.py，删除误导性的 tests/test_basic.py，worker 统一为 NC_TEST_WORKERS；迁移 40 个标准库/语言 builtin 专项 case 到 stdlib_cases/ 并保留历史编号。验证通过：python tests/test_language_cases.py；python tests/test_stdlib.py；python -m pytest tests/test_language_cases.py tests/test_stdlib.py -q；python -m pytest tests/test_projects.py tests/test_builtin_boundary.py tests/test_llvm_backend.py tests/test_type_ref.py -q；python tests/test_stdlib.py case_245_strings_queries.nc。

- 预备推进 fs 向 NC 标准库迁移：新增 str.c_str() 作为 C interop 字符串出口，保持 str 两字段布局但强化 NC 字符串 NUL 终止不变式；引入编译器内置 stdlib NC 源加载，把 fs 从 compiler builtin lowering 移到标准库源码和独立 C support shim；同步 case、边界测试、文档并提交。

- 已推进 fs 向 NC 标准库迁移：新增 str.c_str(): *i8，LLVM 降为非空 C 字符串指针并为零值字符串返回共享空串；NC 字符串分配新增最小私有 __nc_str_alloc_out 以保持 ptr[len] == 0。新增编译器随附 stdlib/fs/fs.nc，s.read_file/write_file 的文件流程改由 NC 源码调用 C stdio extern；xists/remove/rename/mkdir 通过独立
untime/ncfs.c support 对象承载平台/命名冲突 shim，
crt 中旧 fs helper 已移除。更新文档与边界测试，新增 case_248_str_c_str 和 fs support 链接测试。验证通过：python tests/test_language_cases.py；python tests/test_stdlib.py；python -m pytest tests/test_projects.py tests/test_builtin_boundary.py tests/test_llvm_backend.py tests/test_type_ref.py -q。
