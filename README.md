# NC (New C)

NC 是一个“更好的 C”实验编译器：以 LLVM 为后端，自带构建系统和运行时库，使用 GC 管理内存，追求显式、简单、可预测的语言边界。

## 当前状态

- 项目按 case 驱动演进：每个语言能力都由具体 case 推动。
- 编译器当前是 LLVM-only。
- 模块系统采用“目录即模块”：同目录 `.nc` 文件自动互见，跨模块必须显式 `import` 并限定访问。
- 标准库通过显式模块导入使用；标准库 API 见 [docs/stdlib.md](docs/stdlib.md)。
- 构建目标支持 `windows-x64` 和 `linux-x64`。
- 不向前兼容旧语法或旧 API。

## 语言表面很小

NC 刻意控制关键字数量，让语言表面保持小而直接。当前保留词只有：

```text
let if else fun ret err try struct iface enum match for in break new defer nil import extern type true false
```

## 错误处理

NC 采用 Go 风格的显式错误返回，但不采用源码双返回，也不把错误处理写成一串重复的 `if err != nil`。可错调用不能裸用，必须在调用点写清楚：`??` 传播，`!!` 表示必须成功，`try` 拆出成功分支和错误分支，`match e` 对错误分类。

```nc
import fs
import io

fun load_config(): str {
    if !fs.exists("config.nc") {
        err "config missing"
    }
    ret fs.read_file("config.nc")??
}

fun main() {
    try text = load_config() {
        io.println(text)
    } else e {
        let message = match e {
            "config missing" -> "create config.nc first"
            else -> "load failed"
        }
        io.println(message)
    }
}
```

`try` 是语句：成功值只在成功块内可见，`else e` 的错误对象只在错误块内可见。省略 `else` 时，失败行为等同于 `!!`：打印错误和 NC 调用栈后退出。`match e` 使用字符串字面量按错误 message 完整匹配，并且必须有 `else`。

当前边界：v1 可错 callable 只覆盖普通函数和 struct 方法；extern、iface 方法、函数值和闭包暂不支持可错。`error` 是 opaque 内建错误对象；message match 是当前最小错误分类能力，暂不提供公开 inspect/wrap/code/tag API。

## 快速开始

需要 Python 3.12，以及本机可用的 C/LLVM 相关工具链能力。

```powershell
python -m pip install -r requirements.txt
python nc.py run test_cases/case_013_fun.nc
```

`case_013_fun.nc` 内容很短，展示了当前推荐的显式标准库导入方式：

```nc
import io

fun greet() { io.println(42) }
fun main() { greet() }
```

## 常用命令

```powershell
python nc.py run <file.nc|dir>
python nc.py run -c "import io fun main() { io.println(42) }"
python nc.py compile <file.nc|dir>
python nc.py build <file.nc|dir>
python nc.py run --target linux-x64 <file.nc|dir>
python nc.py build --target windows-x64 <file.nc|dir>
```

- `run`：编译并运行。
- `compile`：输出 LLVM IR。
- `build`：生成 `build/main.*` 和可执行文件。
- `--target`：显式选择 `windows-x64` 或 `linux-x64`。

## 回归测试

```powershell
python tests/test_language_cases.py
python tests/test_stdlib.py
python -m pytest tests/test_projects.py tests/test_builtin_boundary.py tests/test_llvm_backend.py tests/test_type_ref.py -q
```

## 仓库结构

- `compiler/`：lexer、parser、typecheck、LLVM codegen 和相关编译器 pass。
- `runtime/`：`ncrt` 私有运行时 ABI 和 C 支撑代码。
- `stdlib/`：NC 标准库源码及少量 C 支撑。
- `test_cases/`：语言能力 case。
- `stdlib_cases/`：标准库和语言级 builtin case。
- `tests/`：case runner、项目级测试和后端/类型工具测试。
- `docs/`：专题文档和历史归档。

## 文档入口

- [design.md](design.md)：语言目标、原则和当前设计边界。
- [docs/stdlib.md](docs/stdlib.md)：标准库 API 边界。
- [docs/generics.md](docs/generics.md)：泛型约束和类型属性矩阵。
- [worklog.md](worklog.md)：当前事实、关键决策和工作记录。

## 开发规则

动手前先读 [design.md](design.md) 和 [worklog.md](worklog.md)。新能力、bug fix 或 refactor 应由 case 推动；工作开始和完成时只 append 更新 `worklog.md`；完成后跑对应回归并提交。
