import os


def normalized_source_path(source_file) -> str:
    path = getattr(source_file, "path", "<memory>") or "<memory>"
    if not path.startswith("<"):
        path = os.path.relpath(os.path.abspath(path))
    return path


def line_col_for_node(node) -> tuple[int, int]:
    source_file = getattr(node, "source_file", None)
    source = getattr(source_file, "source", "") or ""
    span = getattr(node, "span", None)
    if not span:
        return 0, 0
    pos = span[0]
    line = source.count("\n", 0, pos) + 1
    last_nl = source.rfind("\n", 0, pos)
    col = pos + 1 if last_nl < 0 else pos - last_nl
    return line, col


def location_for_node(node) -> tuple[str, int, int]:
    return normalized_source_path(getattr(node, "source_file", None)), *line_col_for_node(node)
