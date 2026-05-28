# worklog

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

