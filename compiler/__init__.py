"""NC Compiler pipeline: symbol table -> type inference -> LLVM IR."""
import os

from compiler.lexer import lex
from compiler.parser import parse, _scan_imports
from compiler.symtab import build_symbol_table
from compiler.typecheck import infer_types
from compiler.generics import monomorphize
from compiler.llvm_codegen import build_llvm_ir, generate_llvm_ir, run_llvm_ir
from compiler.source import Module, SourceFile, annotate_source_file, module_name_from_sources
from compiler.ast import (
    Program, ImportDecl, FunctionDeclaration, StructDecl, IfaceDecl, EnumDecl, FunctionCall, SizeOfType,
    Identifier, StructLiteral, EnumRef, TypeAlias, FunctionExpr, ExternBlock,
)
from compiler.type_ref import rewrite_type

BUILTIN_MODULES = {"io", "runtime", "fs", "os", "strings"}
ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
STDLIB_DIR = os.path.join(ROOT_DIR, "stdlib")
STDLIB_SOURCE_MODULES = {"fs", "os", "strings"}


def _expand_type_str(t: str, aliases: dict[str, str], stack: list[str]) -> str:
    """递归展开类型字符串中的别名。"""
    if not isinstance(t, str):
        return t

    def expand_name(name: str) -> str:
        if name not in aliases:
            return name
        if name in stack:
            raise RuntimeError(f"type alias cycle: {' -> '.join(stack + [name])}")
        stack.append(name)
        result = _expand_type_str(aliases[name], aliases, stack)
        stack.pop()
        return result

    return rewrite_type(t, expand_name)


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
        elif isinstance(node, IfaceDecl):
            node.methods = [(n, [(pn, expand_type(pt)) for pn, pt in params], expand_type(rt)) for n, params, rt in node.methods]
            node.embeds = [expand_type(t) for t in node.embeds]
        elif isinstance(node, FunctionExpr):
            node.params = [(n, expand_type(t)) for n, t in node.params]
            node.return_type = expand_type(node.return_type)
        elif isinstance(node, StructLiteral):
            node.name = expand_type(node.name)
        elif isinstance(node, FunctionCall):
            node.type_args = [expand_type(a) for a in node.type_args]
        elif isinstance(node, SizeOfType):
            node.type_name = expand_type(node.type_name)
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


def parse_module_sources(sources: "list[tuple[str, str]]", *, trusted_stdlib: bool = False) -> Module:
    """Parse source tuples as one directory module.

    当前语义仍是同目录多文件自动互见，但 SourceFile 边界会保留给诊断
    和后续 import/module namespace。
    """
    source_files = [SourceFile(filename, source, trusted_stdlib=trusted_stdlib) for filename, source in sources]
    name, root = module_name_from_sources(source_files)
    module = Module(name, root, source_files)
    token_lists = []
    imported_modules = set()
    for source_file in module.files:
        tokens = list(lex(source_file.source))
        token_lists.append(tokens)
        imported_modules.update(_scan_imports(tokens))
    for source_file, tokens in zip(module.files, token_lists):
        source_file.ast = parse(tokens, imported_modules)
        if trusted_stdlib:
            for stmt in source_file.ast.statements:
                if isinstance(stmt, ExternBlock):
                    stmt.trusted_stdlib = True
                    for fn in stmt.functions:
                        fn.trusted_stdlib = True
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
            if isinstance(stmt, FunctionDeclaration):
                if not stmt.receiver_name:
                    names.add(stmt.name)
            elif isinstance(stmt, (StructDecl, IfaceDecl, EnumDecl)):
                names.add(stmt.name)
            elif isinstance(stmt, ExternBlock):
                for fn in stmt.functions:
                    names.add(fn.name)
    return names


def _qual_type(nc_type, module_name: str, local_names: set[str]):
    if not isinstance(nc_type, str):
        return nc_type

    def qualify_name(name: str) -> str:
        if "." not in name and name in local_names:
            return f"{module_name}.{name}"
        return name

    return rewrite_type(nc_type, qualify_name)


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
            if not node.receiver_name:
                node.name = q(node.name)
            node.return_type = _qual_type(node.return_type, module.name, local_names)
            node.params = [(n, _qual_type(t, module.name, local_names)) for n, t in node.params]
            node.receiver_type = _qual_type(node.receiver_type, module.name, local_names)
        elif isinstance(node, StructDecl):
            node.name = q(node.name)
            node.fields = [(n, _qual_type(t, module.name, local_names)) for n, t in node.fields]
        elif isinstance(node, IfaceDecl):
            node.name = q(node.name)
            node.methods = [
                (n, [(pn, _qual_type(pt, module.name, local_names)) for pn, pt in params],
                 _qual_type(rt, module.name, local_names))
                for n, params, rt in node.methods
            ]
            node.embeds = [_qual_type(t, module.name, local_names) for t in node.embeds]
        elif isinstance(node, EnumDecl):
            node.name = q(node.name)
        elif isinstance(node, ExternBlock):
            for fn in node.functions:
                fn.name = q(fn.name)
                fn.return_type = _qual_type(fn.return_type, module.name, local_names)
                fn.params = [(n, _qual_type(t, module.name, local_names)) for n, t in fn.params]
        elif isinstance(node, FunctionCall):
            node.name = q(node.name)
        elif isinstance(node, SizeOfType):
            node.type_name = _qual_type(node.type_name, module.name, local_names)
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


def parse_project_sources(sources: "list[tuple[str, str]]") -> Module:
    """Parse an entry directory and its imported sibling modules."""
    entry = parse_module_sources(sources)
    project_root = os.path.dirname(entry.root)
    loaded: dict[str, Module] = {}
    order: list[Module] = []
    support_c_sources: list[str] = []
    support_seen: set[str] = set()
    stack: list[str] = []

    def add_stdlib_support_c(module_name: str):
        c_path = os.path.abspath(os.path.join(STDLIB_DIR, module_name, f"{module_name}.c"))
        if not os.path.exists(c_path):
            return
        if c_path in support_seen:
            return
        support_seen.add(c_path)
        support_c_sources.append(c_path)

    def load(module: Module):
        if module.name in stack:
            cycle = " -> ".join(stack + [module.name])
            raise RuntimeError(f"import cycle: {cycle}")
        if module.name in loaded:
            return
        stack.append(module.name)
        loaded[module.name] = module
        for imp in _module_imports(module):
            if imp.module_name in STDLIB_SOURCE_MODULES:
                mod_dir = os.path.join(STDLIB_DIR, imp.module_name)
                files = [os.path.join(mod_dir, n) for n in sorted(os.listdir(mod_dir)) if n.endswith(".nc")]
                child = parse_module_sources([(file, open(file, encoding="utf-8").read()) for file in files], trusted_stdlib=True)
                add_stdlib_support_c(imp.module_name)
                load(child)
                continue
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
        _rewrite_module_names(module, entry=(module.name == entry.name))
    files = []
    for module in order:
        files.extend(module.files)
    return Module(entry.name, entry.root, files, support_c_sources=support_c_sources)


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


def compile_module_to_llvm_ir_with_libs(module: Module) -> tuple[str, list[str], list[str]]:
    """Module → (LLVM IR, link libs, support C sources)."""
    program = _typecheck_module(module)
    link_libs = [
        stmt.lib for stmt in program.statements
        if isinstance(stmt, ExternBlock) and stmt.lib is not None
    ]
    return generate_llvm_ir(program), link_libs, list(module.support_c_sources)


def compile_nc_sources_to_llvm_ir(sources: "list[tuple[str, str]]") -> str:
    """多个 NC 源码片段 → 单个 LLVM IR。"""
    return compile_module_to_llvm_ir(parse_project_sources(sources))


def compile_nc_sources_with_libs(sources: "list[tuple[str, str]]") -> tuple[str, list[str], list[str]]:
    """多个 NC 源码片段 → (LLVM IR, link libs, support C sources)."""
    return compile_module_to_llvm_ir_with_libs(parse_project_sources(sources))


def compile_nc_to_llvm_ir(nc_source: str) -> str:
    """NC 源码 → LLVM IR（三 pass）。"""
    return compile_nc_sources_to_llvm_ir([("<memory>", nc_source)])
