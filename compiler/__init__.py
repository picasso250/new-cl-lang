"""NC Compiler pipeline: symbol table -> type inference -> LLVM IR."""
import os

from compiler.lexer import lex
from compiler.parser import parse
from compiler.symtab import build_symbol_table
from compiler.typecheck import infer_types
from compiler.generics import monomorphize
from compiler.llvm_codegen import build_llvm_ir, generate_llvm_ir, run_llvm_ir
from compiler.source import Module, SourceFile, annotate_source_file, module_name_from_sources
from compiler.ast import (
    Program, ImportDecl, FunctionDeclaration, StructDecl, EnumDecl, FunctionCall,
    Identifier, StructLiteral, EnumRef, MethodCall, TypeAlias, FunctionExpr, VariableDeclaration,
    ExternBlock,
    ArrayLiteral, SliceLiteral
)

BUILTIN_MODULES = {"io", "runtime"}


def _split_top_level_comma(s: str) -> list[str]:
    """按顶层逗号分割，忽略括号内的逗号。"""
    parts = []
    start = 0
    depth = 0
    for i, ch in enumerate(s):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(s[start:i])
            start = i + 1
    parts.append(s[start:])
    return [p.strip() for p in parts if p.strip()]


def _expand_type_str(t: str, aliases: dict[str, str], stack: list[str]) -> str:
    """递归展开类型字符串中的别名。"""
    if not isinstance(t, str):
        return t
    # 指针 / nullable 指针
    for prefix in ("?*", "*", "[]"):
        if t.startswith(prefix):
            return prefix + _expand_type_str(t[len(prefix):], aliases, stack)
    # 定长数组 [N]T
    if t.startswith("[") and "]" in t:
        head, tail = t.split("]", 1)
        return head + "]" + _expand_type_str(tail, aliases, stack)
    # 函数类型 fn(args)->ret
    if t.startswith("fn("):
        close = t.find(")->")
        if close >= 0:
            args_str = t[3:close]
            args = _split_top_level_comma(args_str) if args_str else []
            ret = t[close + 3:]
            return f"fn({','.join(_expand_type_str(a, aliases, stack) for a in args)})->{_expand_type_str(ret, aliases, stack)}"
    # 泛型类型应用 Foo[T, U]
    if "[" in t and t.endswith("]"):
        lb = t.find("[")
        base = t[:lb]
        args_s = t[lb + 1:-1]
        args = _split_top_level_comma(args_s)
        expanded_args = [_expand_type_str(a.strip(), aliases, stack) for a in args]
        return f"{_expand_type_str(base, aliases, stack)}[{','.join(expanded_args)}]"
    # 简单别名名
    if t in aliases:
        if t in stack:
            raise RuntimeError(f"type alias cycle: {' -> '.join(stack + [t])}")
        stack.append(t)
        result = _expand_type_str(aliases[t], aliases, stack)
        stack.pop()
        return result
    return t


def _expand_type_aliases_in_module(module: Module):
    """收集 TypeAlias 定义并从 AST 中展开。"""
    aliases: dict[str, str] = {}

    # 第一遍：收集别名定义并验证
    for source_file in module.files:
        remaining = []
        for stmt in source_file.ast.statements:
            if isinstance(stmt, TypeAlias):
                if stmt.name in aliases:
                    raise RuntimeError(f"duplicate type alias '{stmt.name}'")
                aliases[stmt.name] = stmt.target_type
            else:
                remaining.append(stmt)
        source_file.ast.statements = remaining

    if not aliases:
        return

    # 验证别名无循环（即使未使用也检测）
    for name in list(aliases.keys()):
        _expand_type_str(name, aliases, [])

    # 第二遍：展开 AST 中所有类型字符串
    def expand_type(t):
        return _expand_type_str(t, aliases, [])

    def walk(node):
        if not hasattr(node, "__dict__"):
            return
        if isinstance(node, FunctionDeclaration):
            node.params = [(n, expand_type(t)) for n, t in node.params]
            node.return_type = expand_type(node.return_type)
            node.receiver_type = expand_type(node.receiver_type)
        elif isinstance(node, StructDecl):
            node.fields = [(n, expand_type(t)) for n, t in node.fields]
        elif isinstance(node, FunctionExpr):
            node.params = [(n, expand_type(t)) for n, t in node.params]
            node.return_type = expand_type(node.return_type)
        elif isinstance(node, StructLiteral):
            node.name = expand_type(node.name)
        elif isinstance(node, FunctionCall):
            node.type_args = [expand_type(a) for a in node.type_args]
        for key in ("annotation", "elem_type"):
            if hasattr(node, key):
                setattr(node, key, expand_type(getattr(node, key)))
        for value in list(node.__dict__.values()):
            if isinstance(value, SourceFile):
                continue
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, tuple):
                        for part in item:
                            walk(part)
                    else:
                        walk(item)
            elif isinstance(value, tuple):
                for item in value:
                    walk(item)
            else:
                walk(value)

    for source_file in module.files:
        for stmt in source_file.ast.statements:
            walk(stmt)


def parse_module_sources(sources: "list[tuple[str, str]]") -> Module:
    """Parse source tuples as one directory module.

    当前语义仍是同目录多文件自动互见，但 SourceFile 边界会保留给诊断
    和后续 import/module namespace。
    """
    source_files = [SourceFile(filename, source) for filename, source in sources]
    name, root = module_name_from_sources(source_files)
    module = Module(name, root, source_files)
    for source_file in module.files:
        tokens = list(lex(source_file.source))
        source_file.ast = parse(tokens)
        annotate_source_file(source_file.ast, source_file)
    _expand_type_aliases_in_module(module)
    return module


def _module_imports(module: Module) -> list[ImportDecl]:
    imports = []
    for source_file in module.files:
        for stmt in source_file.ast.statements:
            if isinstance(stmt, ImportDecl):
                imports.append(stmt)
    return imports


def _top_names(module: Module) -> set[str]:
    names = set()
    for source_file in module.files:
        for stmt in source_file.ast.statements:
            if isinstance(stmt, (FunctionDeclaration, StructDecl, EnumDecl)):
                names.add(stmt.name)
            elif isinstance(stmt, ExternBlock):
                for fn in stmt.functions:
                    names.add(fn.name)
    return names


def _qual_type(nc_type, module_name: str, local_names: set[str]):
    if not isinstance(nc_type, str):
        return nc_type
    if "." in nc_type:
        return nc_type
    for prefix in ("?*", "*", "[]"):
        if nc_type.startswith(prefix):
            return prefix + _qual_type(nc_type[len(prefix):], module_name, local_names)
    if nc_type.startswith("[") and "]" in nc_type:
        head, tail = nc_type.split("]", 1)
        return head + "]" + _qual_type(tail, module_name, local_names)
    if nc_type.endswith("]") and "[" in nc_type:
        base, rest = nc_type.split("[", 1)
        args_s = rest[:-1]
        args = []
        start = 0
        depth = 0
        for i, ch in enumerate(args_s):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
            elif ch == "," and depth == 0:
                args.append(args_s[start:i])
                start = i + 1
        args.append(args_s[start:])
        qbase = _qual_type(base, module_name, local_names)
        return f"{qbase}[{','.join(_qual_type(arg.strip(), module_name, local_names) for arg in args if arg.strip())}]"
    if nc_type in local_names:
        return f"{module_name}.{nc_type}"
    return nc_type


def _rewrite_module_names(module: Module, entry: bool):
    if entry:
        return
    local_names = _top_names(module)

    def q(name: str) -> str:
        if "." not in name and name in local_names:
            return f"{module.name}.{name}"
        return name

    def walk(node):
        if not hasattr(node, "__dict__"):
            return
        if isinstance(node, FunctionDeclaration):
            node.name = q(node.name)
            node.return_type = _qual_type(node.return_type, module.name, local_names)
            node.params = [(n, _qual_type(t, module.name, local_names)) for n, t in node.params]
            node.receiver_type = _qual_type(node.receiver_type, module.name, local_names)
        elif isinstance(node, StructDecl):
            node.name = q(node.name)
            node.fields = [(n, _qual_type(t, module.name, local_names)) for n, t in node.fields]
        elif isinstance(node, EnumDecl):
            node.name = q(node.name)
        elif isinstance(node, ExternBlock):
            for fn in node.functions:
                fn.return_type = _qual_type(fn.return_type, module.name, local_names)
                fn.params = [(n, _qual_type(t, module.name, local_names)) for n, t in fn.params]
        elif isinstance(node, FunctionCall):
            node.name = q(node.name)
        elif isinstance(node, Identifier):
            node.name = q(node.name)
        elif isinstance(node, StructLiteral):
            node.name = q(node.name)
        elif isinstance(node, EnumRef):
            node.enum_name = q(node.enum_name)
        for value in list(node.__dict__.values()):
            if isinstance(value, SourceFile):
                continue
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, tuple):
                        for part in item:
                            walk(part)
                    else:
                        walk(item)
            elif isinstance(value, tuple):
                for item in value:
                    walk(item)
            else:
                walk(value)

    for source_file in module.files:
        for stmt in source_file.ast.statements:
            walk(stmt)


def _rewrite_import_calls(module: Module):
    import_names = {imp.module_name for imp in _module_imports(module)}

    def walk_value(value):
        if isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, tuple):
                    value[i] = tuple(walk(part) for part in item)
                else:
                    value[i] = walk(item)
            return value
        if isinstance(value, tuple):
            return tuple(walk(item) for item in value)
        return walk(value)

    def walk(node):
        if not hasattr(node, "__dict__"):
            return node
        if isinstance(node, MethodCall) and isinstance(node.obj, Identifier) and node.obj.name in import_names:
            repl = FunctionCall(f"{node.obj.name}.{node.method}", node.args)
            if hasattr(node, "source_file"):
                repl.source_file = node.source_file
            if hasattr(node, "span"):
                repl.span = node.span
            repl.args = [walk(arg) for arg in repl.args]
            return repl
        for key, value in list(node.__dict__.items()):
            if isinstance(value, SourceFile):
                continue
            setattr(node, key, walk_value(value))
        return node

    for source_file in module.files:
        source_file.ast = walk(source_file.ast)


def parse_project_sources(sources: "list[tuple[str, str]]") -> Module:
    """Parse an entry directory and its imported sibling modules."""
    entry = parse_module_sources(sources)
    if not entry.root:
        _rewrite_import_calls(entry)
        return entry
    project_root = os.path.dirname(entry.root)
    loaded: dict[str, Module] = {}
    order: list[Module] = []
    stack: list[str] = []

    def load(module: Module):
        if module.name in stack:
            cycle = " -> ".join(stack + [module.name])
            raise RuntimeError(f"import cycle: {cycle}")
        if module.name in loaded:
            return
        stack.append(module.name)
        loaded[module.name] = module
        for imp in _module_imports(module):
            if imp.module_name in BUILTIN_MODULES:
                continue
            mod_dir = os.path.join(project_root, imp.module_name)
            if not os.path.isdir(mod_dir):
                raise RuntimeError(f"module '{imp.module_name}' not found: {mod_dir}")
            files = [os.path.join(mod_dir, n) for n in sorted(os.listdir(mod_dir)) if n.endswith(".nc")]
            if not files:
                raise RuntimeError(f"module '{imp.module_name}' has no .nc files: {mod_dir}")
            child = parse_module_sources([(file, open(file, encoding="utf-8").read()) for file in files])
            load(child)
        stack.pop()
        order.append(module)

    load(entry)
    for module in order:
        _rewrite_import_calls(module)
    for module in order:
        _rewrite_module_names(module, entry=(module.name == entry.name))
    files = []
    for module in order:
        files.extend(module.files)
    return Module(entry.name, entry.root, files)


def _typecheck_module(module: Module) -> Program:
    program = module.to_program()
    program = monomorphize(program)

    # Pass 1: 建符号表
    symtab = build_symbol_table(program)

    # Pass 2: 类型推断
    infer_types(program, symtab)
    return program


def compile_module_to_llvm_ir(module: Module) -> str:
    """Module → LLVM IR（三 pass）。"""
    program = _typecheck_module(module)
    return generate_llvm_ir(program)


def compile_nc_sources_to_llvm_ir(sources: "list[tuple[str, str]]") -> str:
    """多个 NC 源码片段 → 单个 LLVM IR。"""
    return compile_module_to_llvm_ir(parse_project_sources(sources))


def compile_nc_to_llvm_ir(nc_source: str) -> str:
    """NC 源码 → LLVM IR（三 pass）。"""
    return compile_nc_sources_to_llvm_ir([("<memory>", nc_source)])
