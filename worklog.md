# worklog

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
