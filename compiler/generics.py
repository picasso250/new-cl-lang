"""Frontend monomorphization for explicit generic functions and structs."""

from __future__ import annotations

import copy
import re

from compiler.ast import (
    FunctionCall, FunctionDeclaration, GenericFunctionValue, Identifier, IndexAccess,
    MapLiteral, Program, SizeOfType, StructDecl, StructLiteral,
)
from compiler.constraints import satisfies_constraint
from compiler.type_ref import (
    ArrayTypeRef,
    GenericType,
    NamedType,
    PointerType,
    SliceType,
    TypeRefBase,
    format_type_ref,
    parse_type_app,
    parse_type_ref,
    rewrite_type_ref,
    type_key,
)


class GenericError(Exception):
    pass


def _mangle_type(t: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", type_key(t) or "").strip("_")


def _instance_name(name: str, args: list[str]) -> str:
    return f"{name}__{'__'.join(_mangle_type(arg) for arg in args)}"


def _sub_type(t, subst: dict[str, str]):
    if t is None:
        return t
    return rewrite_type_ref(t, lambda name: subst.get(name, name))


def _normalize_call_type_args(call: FunctionCall):
    if call.type_args:
        return
    app = parse_type_app(call.name)
    if app:
        call.name, call.type_args = app


def _walk_values(node, fn, *, skip_param_defaults: bool = False):
    if isinstance(node, TypeRefBase) or not hasattr(node, "__dict__") or node.__class__.__name__ == "SourceFile":
        return
    fn(node)
    for key, value in list(node.__dict__.items()):
        if skip_param_defaults and node.__class__.__name__ == "Param" and key == "default":
            continue
        if isinstance(value, list):
            for item in value:
                if isinstance(item, tuple):
                    for part in item:
                        _walk_values(part, fn, skip_param_defaults=skip_param_defaults)
                elif item.__class__.__name__ != "SourceFile":
                    _walk_values(item, fn, skip_param_defaults=skip_param_defaults)
        elif isinstance(value, tuple):
            for item in value:
                _walk_values(item, fn, skip_param_defaults=skip_param_defaults)
        else:
            if value.__class__.__name__ != "SourceFile":
                _walk_values(value, fn, skip_param_defaults=skip_param_defaults)


def _substitute_node(node, subst: dict[str, str]):
    def apply(n):
        if isinstance(n, FunctionDeclaration):
            for param in n.params:
                param.type = _sub_type(param.type, subst)
            n.return_type = _sub_type(n.return_type, subst)
            n.receiver_type = _sub_type(n.receiver_type, subst)
            n.type_params = []
            n.type_param_constraints = {}
        elif isinstance(n, StructDecl):
            n.fields = [(name, _sub_type(t, subst)) for name, t in n.fields]
            n.embedded_fields = set(getattr(n, "embedded_fields", set()))
            n.type_params = []
            n.type_param_constraints = {}
        elif isinstance(n, StructLiteral):
            n.name = _sub_type(n.name, subst)
        elif isinstance(n, MapLiteral):
            if n.map_type is not None:
                n.map_type = _sub_type(n.map_type, subst)
        elif isinstance(n, FunctionCall):
            _normalize_call_type_args(n)
            n.type_args = [_sub_type(t, subst) for t in n.type_args]
        elif isinstance(n, GenericFunctionValue):
            n.type_args = [_sub_type(t, subst) for t in n.type_args]
        elif hasattr(n, "generic_type_args_candidate"):
            n.generic_type_args_candidate = [_sub_type(t, subst) for t in n.generic_type_args_candidate]
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
    concrete_funcs = {}
    for stmt in program.statements:
        if isinstance(stmt, FunctionDeclaration) and stmt.type_params:
            if stmt.receiver_name:
                raise GenericError("generic methods are not supported in generic v1")
            generic_funcs[stmt.name] = stmt
        elif isinstance(stmt, StructDecl) and stmt.type_params:
            generic_structs[stmt.name] = stmt
        else:
            if isinstance(stmt, FunctionDeclaration):
                concrete_funcs[stmt.name] = stmt
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
        for param, arg in zip(tmpl.type_params, args):
            constraint = tmpl.type_param_constraints.get(param, "any")
            if not satisfies_constraint(arg, constraint):
                raise GenericError(f"generic type {base}: type arg {arg} does not satisfy {constraint}")
        key = (base, tuple(args))
        if key in made_structs:
            return
        made_structs.add(key)
        subst = dict(zip(tmpl.type_params, args))
        inst = _substitute_node(copy.deepcopy(tmpl), subst)
        inst.name = _instance_name(base, args)
        inst._generic_origin_kind = "type"
        inst._generic_origin_name = base
        inst._generic_constraints = [(param, arg, tmpl.type_param_constraints.get(param, "any"))
                                     for param, arg in zip(tmpl.type_params, args)]
        generated.append(inst)

    def request_func(base, args):
        if base not in generic_funcs:
            if args:
                raise GenericError(f"function {base} is not generic")
            return
        tmpl = generic_funcs[base]
        if len(args) != len(tmpl.type_params):
            raise GenericError(f"generic function {base}: expected {len(tmpl.type_params)} type args, got {len(args)}")
        for param, arg in zip(tmpl.type_params, args):
            constraint = tmpl.type_param_constraints.get(param, "any")
            if not satisfies_constraint(arg, constraint):
                raise GenericError(f"generic function {base}: type arg {arg} does not satisfy {constraint}")
        key = (base, tuple(args))
        if key in made_funcs:
            return
        made_funcs.add(key)
        subst = dict(zip(tmpl.type_params, args))
        inst = _substitute_node(copy.deepcopy(tmpl), subst)
        inst.name = _instance_name(base, args)
        inst._generic_origin_kind = "function"
        inst._generic_origin_name = base
        inst._generic_constraints = [(param, arg, tmpl.type_param_constraints.get(param, "any"))
                                     for param, arg in zip(tmpl.type_params, args)]
        concrete_funcs[inst.name] = inst
        generated.append(inst)

    def rewrite_type(t):
        if t is None:
            return t
        ref = parse_type_ref(t)
        if isinstance(ref, PointerType):
            return PointerType(rewrite_type(ref.inner), ref.nullable)
        if isinstance(ref, SliceType):
            return SliceType(rewrite_type(ref.elem))
        if isinstance(ref, ArrayTypeRef):
            return ArrayTypeRef(ref.length, rewrite_type(ref.elem))
        if isinstance(ref, GenericType) and isinstance(ref.base, NamedType):
            base = ref.base.name
            args = [rewrite_type(a) for a in ref.args]
            if base == "map":
                return GenericType(NamedType("map"), tuple(parse_type_ref(a) for a in args))
            request_struct(base, args)
            return NamedType(_instance_name(base, args))
        t_s = type_key(ref)
        if t_s in generic_structs:
            raise GenericError(f"generic type {t_s} requires explicit type args")
        return ref

    def rewrite_node(n):
        if isinstance(n, FunctionDeclaration):
            for param in n.params:
                if param.type is not None:
                    param.type = rewrite_type(param.type)
            n.return_type = rewrite_type(n.return_type)
            n.receiver_type = rewrite_type(n.receiver_type)
        elif isinstance(n, StructDecl):
            n.fields = [(name, rewrite_type(t)) for name, t in n.fields]
            n.embedded_fields = set(getattr(n, "embedded_fields", set()))
        elif isinstance(n, StructLiteral):
            n.name = rewrite_type(n.name)
        elif isinstance(n, MapLiteral):
            if n.map_type is not None:
                n.map_type = rewrite_type(n.map_type)
        elif isinstance(n, FunctionCall):
            _normalize_call_type_args(n)
            if n.name in generic_funcs and not n.type_args:
                raise GenericError(f"generic function {n.name} requires explicit type args")
            if n.type_args:
                args = [rewrite_type(a) for a in n.type_args]
                if n.name == "map":
                    from compiler.type_ref import GenericType, NamedType, parse_type_ref
                    n.name = format_type_ref(GenericType(NamedType("map"), tuple(parse_type_ref(a) for a in args)))
                    n.type_args = []
                    return
                request_func(n.name, args)
                n.name = _instance_name(n.name, args)
                n.type_args = []
        elif isinstance(n, GenericFunctionValue):
            if not n.type_args:
                return
            args = [rewrite_type(a) for a in n.type_args]
            request_func(n.name, args)
            n.name = _instance_name(n.name, args)
            n.type_args = []
        elif isinstance(n, IndexAccess):
            type_args = getattr(n, "generic_type_args_candidate", None)
            if (type_args
                    and isinstance(n.obj, Identifier)
                    and n.obj.name in generic_funcs):
                args = [rewrite_type(a) for a in type_args]
                request_func(n.obj.name, args)
                n.__class__ = GenericFunctionValue  # pyright: ignore[reportAttributeAccessIssue]
                n.name = _instance_name(n.obj.name, args)
                n.type_args = []
                if hasattr(n, "obj"):
                    delattr(n, "obj")
                if hasattr(n, "index"):
                    delattr(n, "index")
                if hasattr(n, "generic_type_args_candidate"):
                    delattr(n, "generic_type_args_candidate")
        elif isinstance(n, SizeOfType):
            n.type_name = rewrite_type(n.type_name)
        for key in ("annotation", "elem_type"):
            if hasattr(n, key):
                setattr(n, key, rewrite_type(getattr(n, key)))

    def request_omitted_defaults(call: FunctionCall):
        fn = concrete_funcs.get(call.name)
        if fn is None:
            return
        if len(call.args) >= len(fn.params):
            return
        for param in fn.params[len(call.args):]:
            if param.default is not None:
                _walk_values(param.default, rewrite_node)

    changed = True
    while changed:
        before = len(generated)
        for stmt in ordinary:
            _walk_values(stmt, rewrite_node)
        for stmt in generated:
            _walk_values(stmt, rewrite_node, skip_param_defaults=True)
        for stmt in ordinary + generated:
            def request_call_defaults(n):
                if isinstance(n, FunctionCall):
                    request_omitted_defaults(n)
            _walk_values(stmt, request_call_defaults, skip_param_defaults=True)
        changed = len(generated) != before

    return Program(ordinary + generated)
