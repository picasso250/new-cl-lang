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
