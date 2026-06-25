# NC 内部 ABI 与构建规范

> 本文件记录内部 ABI 规则、模块对象生成、符号命名和缓存策略。`design.md` 只保留原则和 why；本文件承载实现规范细节。

## 内部 ABI 章程

- NC 内部 ABI 不承诺用户可依赖的长期二进制稳定性。
- 用户源码不得声明 `__nc*` 保留前缀符号；`ncrt` 和编译器生成 helper 使用该前缀。
- `main` 作为 hosted C runtime 入口保持 C 符号名 `main`。
- 非 extern 的 NC 函数、方法、闭包、函数值 thunk、iface thunk/vtable、map descriptor/hash/eq 等符号由统一 ABI 命名入口生成。
- 内部 ABI 符号采用可读骨架加完整规范签名短 hash；完整解释写入 `abi-manifest.json`。

## 模块对象与 debug 构建

- `build --keep-objs` 下，每个 NC 模块生成一个对象文件；`ncrt` 和标准库伴随 C 文件仍各自生成独立对象。
- 模块对象的 debug manifest 记录模块对象、链接输入、导出符号、跨模块需求和泛型实例需求。
- `abi-manifest.json` 记录内部 ABI 版本的完整解释。

## 泛型实例与跨模块依赖

- 泛型实例归定义模块生成；外部模块新增泛型实例需求时，定义模块对象的输入指纹会变化并需要重编译或重新取缓存。
- 模块对象缓存以目标、内部 ABI 版本和模块 LLVM IR 指纹为保守正确性边界；IR 变化即视为缓存失效。

## 构建产物

- 标准 `build` 输出可执行文件及运行时对象。
- `build --keep-objs` 保留每个 NC 模块对象、模块 LLVM IR 和 ABI manifest，便于调试和观察链接阶段。
