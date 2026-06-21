"""Source-file and module model for NC compilation."""

from dataclasses import dataclass, field
import os

from compiler.ast import Program


@dataclass
class SourceFile:
    path: str
    source: str
    ast: Program | None = None
    trusted_stdlib: bool = False
    module_name: str = "<memory>"

    def __post_init__(self):
        if not self.path:
            self.path = "<memory>"


@dataclass
class Module:
    name: str
    root: str
    files: list[SourceFile] = field(default_factory=list)
    support_c_sources: list[str] = field(default_factory=list)

    def to_program(self) -> Program:
        statements = []
        for source_file in self.files:
            if source_file.ast is None:
                continue
            statements.extend(source_file.ast.statements)
        return Program(statements)


def module_name_from_sources(sources: list[SourceFile]) -> tuple[str, str]:
    if not sources:
        return "<empty>", ""
    first = sources[0].path
    if first.startswith("<") and first.endswith(">"):
        return first, ""
    common = os.path.commonpath([os.path.abspath(s.path) for s in sources])
    if os.path.isfile(common):
        root = os.path.dirname(common)
    else:
        root = common
    return os.path.basename(root) or root, root


def annotate_source_file(node, source_file: SourceFile):
    """Attach source-file ownership to every AST node in a parsed file."""
    if not hasattr(node, "__dict__"):
        return
    node.source_file = source_file
    for value in list(node.__dict__.values()):
        if value is source_file:
            continue
        if isinstance(value, list):
            for item in value:
                if isinstance(item, tuple):
                    for part in item:
                        annotate_source_file(part, source_file)
                else:
                    annotate_source_file(item, source_file)
        elif isinstance(value, tuple):
            for item in value:
                annotate_source_file(item, source_file)
        else:
            annotate_source_file(value, source_file)
