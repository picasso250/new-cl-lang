import pytest

from compiler import _expand_type_str
from compiler.type_ref import (
    format_type_ref,
    parse_array_type,
    parse_fn_type,
    parse_map_type,
    parse_slice_type,
    parse_type_app,
    parse_type_ref,
    rewrite_type,
)


@pytest.mark.parametrize(
    "type_string",
    [
        "str",
        "*User",
        "?*User",
        "[]str",
        "[3]i32",
        "fn(i32,[]str)->?*User",
        "Box[Box[str]]",
        "foo.Box[str]",
        "map[str,i32]",
    ],
)
def test_type_ref_round_trip(type_string):
    assert format_type_ref(parse_type_ref(type_string)) == type_string


def test_type_ref_extractors_handle_nested_types():
    assert parse_fn_type("fn(i32,Box[[]str])->?*User") == (["i32", "Box[[]str]"], "?*User")
    assert parse_array_type("[3]Box[str]") == (3, "Box[str]")
    assert parse_slice_type("[]foo.Box[str]") == "foo.Box[str]"
    assert parse_type_app("foo.Box[Box[str]]") == ("foo.Box", ["Box[str]"])
    assert parse_map_type("map[str,Box[i32]]") == ["str", "Box[i32]"]


def test_rewrite_type_rewrites_only_named_components():
    aliases = {"Name": "str", "UserBox": "foo.Box[User]"}

    assert rewrite_type("fn(Name,[]UserBox)->?*User", lambda n: aliases.get(n, n)) == (
        "fn(str,[]foo.Box[User])->?*User"
    )


def test_alias_expansion_uses_type_ref_and_keeps_cycle_error():
    aliases = {"Name": "str", "Names": "[]Name", "Fn": "fn(Names)->Name"}
    assert _expand_type_str("Fn", aliases, []) == "fn([]str)->str"

    with pytest.raises(RuntimeError, match="type alias cycle: A -> B -> A"):
        _expand_type_str("A", {"A": "B", "B": "A"}, [])
