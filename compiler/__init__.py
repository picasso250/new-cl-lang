"""
NC Compiler —— 三 pass 流水线：建符号表 → 类型推断 → 生成 C 代码。
"""
import subprocess
import tempfile
import os

from compiler.lexer import lex
from compiler.parser import parse
from compiler.symtab import build_symbol_table
from compiler.typecheck import infer_types
from compiler.codegen import generate_c
from compiler.source import Module, SourceFile, annotate_source_file, module_name_from_sources
from compiler.ast import (
    Program, ImportDecl, FunctionDeclaration, StructDecl, EnumDecl, FunctionCall,
    Identifier, StructLiteral, EnumRef, MethodCall
)

BUILTIN_MODULES = {"io"}


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


def compile_module_to_c(module: Module) -> str:
    """Module → C 源码（三 pass）。"""
    program = module.to_program()

    # Pass 1: 建符号表
    symtab = build_symbol_table(program)

    # Pass 2: 类型推断
    infer_types(program, symtab)

    # Pass 3: 代码生成
    return generate_c(program)


def compile_nc_sources_to_c(sources: "list[tuple[str, str]]") -> str:
    """多个 NC 源码片段 → 单个 C 源码。"""
    return compile_module_to_c(parse_project_sources(sources))


def compile_nc_to_c(nc_source: str) -> str:
    """NC 源码 → C 源码（三 pass）。"""
    return compile_nc_sources_to_c([("<memory>", nc_source)])


def run_c_code(c_code: str) -> "tuple[str, str, int]":
    """C 源码 → 编译 → 运行 → 返回 (stdout, stderr, returncode)。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        c_path = os.path.join(tmpdir, "out.c")
        exe_path = os.path.join(tmpdir, "out.exe")

        with open(c_path, "w", encoding="utf-8") as f:
            f.write(c_code)

        result = subprocess.run(
            ["gcc", c_path, "-o", exe_path],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"C compilation failed:\n{result.stderr}")

        result = subprocess.run(
            [exe_path],
            capture_output=True, text=True
        )
        return result.stdout, result.stderr, result.returncode


def build_c_code(c_code: str, out_dir: str, name: str = "main") -> "tuple[str, str]":
    """C 源码 → build 目录产物，返回 (c_path, exe_path)。"""
    os.makedirs(out_dir, exist_ok=True)
    c_path = os.path.join(out_dir, f"{name}.c")
    exe_path = os.path.join(out_dir, f"{name}.exe")

    with open(c_path, "w", encoding="utf-8") as f:
        f.write(c_code)

    result = subprocess.run(
        ["gcc", c_path, "-o", exe_path],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"C compilation failed:\n{result.stderr}")

    return c_path, exe_path
