"""Frontend monomorphization for explicit generic functions and structs."""

from __future__ import annotations

import copy
import re

from compiler.ast import FunctionCall, FunctionDeclaration, Program, SizeOfType, StructDecl, StructLiteral
from compiler.type_ref import parse_type_app, rewrite_type as rewrite_type_ref


class GenericError(Exception):
    pass


def _mangle_type(t: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", t).strip("_")


def _instance_name(name: str, args: list[str]) -> str:
    return f"{name}__{'__'.join(_mangle_type(arg) for arg in args)}"


def _sub_type(t, subst: dict[str, str]):
    if not isinstance(t, str):
        return t
    return rewrite_type_ref(t, lambda name: subst.get(name, name))


def _normalize_call_type_args(call: FunctionCall):
    if call.type_args:
        return
    app = parse_type_app(call.name)
    if app:
        call.name, call.type_args = app


def _walk_values(node, fn):
    if not hasattr(node, "__dict__") or node.__class__.__name__ == "SourceFile":
        return
    fn(node)
    for value in list(node.__dict__.values()):
        if isinstance(value, list):
            for item in value:
                if isinstance(item, tuple):
                    for part in item:
                        _walk_values(part, fn)
                elif item.__class__.__name__ != "SourceFile":
                    _walk_values(item, fn)
        elif isinstance(value, tuple):
            for item in value:
                _walk_values(item, fn)
        else:
            if value.__class__.__name__ != "SourceFile":
                _walk_values(value, fn)


def _substitute_node(node, subst: dict[str, str]):
    def apply(n):
        if isinstance(n, FunctionDeclaration):
            for param in n.params:
                param.type = _sub_type(param.type, subst)
            n.return_type = _sub_type(n.return_type, subst)
            n.receiver_type = _sub_type(n.receiver_type, subst)
            n.type_params = []
        elif isinstance(n, StructDecl):
            n.fields = [(name, _sub_type(t, subst)) for name, t in n.fields]
            n.type_params = []
        elif isinstance(n, StructLiteral):
            n.name = _sub_type(n.name, subst)
        elif isinstance(n, FunctionCall):
            _normalize_call_type_args(n)
            n.type_args = [_sub_type(t, subst) for t in n.type_args]
        elif isinstance(n, SizeOfType):
            n.type_name = _sub_type(n.type_name, subst)
        for key in ("annotation", "elem_type"):
            if hasattr(n, key):
                setattr(n, key, _sub_type(getattr(n, key), subst))
    _walk_values(node, apply)
    return node


def monomorphize(program: Program) -> Program:
    generic_funcs = {}
    generic_structs = {}
    ordinary = []
    for stmt in program.statements:
        if isinstance(stmt, FunctionDeclaration) and stmt.type_params:
            if stmt.receiver_name:
                raise GenericError("generic methods are not supported in generic v1")
            generic_funcs[stmt.name] = stmt
        elif isinstance(stmt, StructDecl) and stmt.type_params:
            generic_structs[stmt.name] = stmt
        else:
            ordinary.append(stmt)

    generated = []
    made_funcs = set()
    made_structs = set()

    def request_struct(base, args):
        if base not in generic_structs:
            if args:
                raise GenericError(f"type {base} is not generic")
            return
        tmpl = generic_structs[base]
        if len(args) != len(tmpl.type_params):
            raise GenericError(f"generic type {base}: expected {len(tmpl.type_params)} type args, got {len(args)}")
        key = (base, tuple(args))
        if key in made_structs:
            return
        made_structs.add(key)
        subst = dict(zip(tmpl.type_params, args))
        inst = _substitute_node(copy.deepcopy(tmpl), subst)
        inst.name = _instance_name(base, args)
        generated.append(inst)

    def request_func(base, args):
        if base not in generic_funcs:
            if args:
                raise GenericError(f"function {base} is not generic")
            return
        tmpl = generic_funcs[base]
        if len(args) != len(tmpl.type_params):
            raise GenericError(f"generic function {base}: expected {len(tmpl.type_params)} type args, got {len(args)}")
        key = (base, tuple(args))
        if key in made_funcs:
            return
        made_funcs.add(key)
        subst = dict(zip(tmpl.type_params, args))
        inst = _substitute_node(copy.deepcopy(tmpl), subst)
        inst.name = _instance_name(base, args)
        generated.append(inst)

    def rewrite_type(t):
        if not isinstance(t, str):
            return t
        for prefix in ("?*", "*", "[]"):
            if t.startswith(prefix):
                return prefix + rewrite_type(t[len(prefix):])
        if t.startswith("[") and "]" in t:
            head, tail = t.split("]", 1)
            return head + "]" + rewrite_type(tail)
        app = parse_type_app(t)
        if app:
            base, args = app
            args = [rewrite_type(a) for a in args]
            if base == "map":
                return f"map[{','.join(args)}]"
            request_struct(base, args)
            return _instance_name(base, args)
        if t in generic_structs:
            raise GenericError(f"generic type {t} requires explicit type args")
        return t

    def rewrite_node(n):
        if isinstance(n, FunctionDeclaration):
            for param in n.params:
                param.type = rewrite_type(param.type)
            n.return_type = rewrite_type(n.return_type)
            n.receiver_type = rewrite_type(n.receiver_type)
        elif isinstance(n, StructDecl):
            n.fields = [(name, rewrite_type(t)) for name, t in n.fields]
        elif isinstance(n, StructLiteral):
            n.name = rewrite_type(n.name)
        elif isinstance(n, FunctionCall):
            _normalize_call_type_args(n)
            if n.name in generic_funcs and not n.type_args:
                raise GenericError(f"generic function {n.name} requires explicit type args")
            if n.type_args:
                args = [rewrite_type(a) for a in n.type_args]
                if n.name == "map":
                    n.name = f"map[{','.join(args)}]"
                    n.type_args = []
                    return
                request_func(n.name, args)
                n.name = _instance_name(n.name, args)
                n.type_args = []
        elif isinstance(n, SizeOfType):
            n.type_name = rewrite_type(n.type_name)
        for key in ("annotation", "elem_type"):
            if hasattr(n, key):
                setattr(n, key, rewrite_type(getattr(n, key)))

    changed = True
    while changed:
        before = len(generated)
        for stmt in ordinary + generated:
            _walk_values(stmt, rewrite_node)
        changed = len(generated) != before

    return Program(ordinary + generated)
