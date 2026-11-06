import zipfile
from collections.abc import Iterator
from pathlib import Path

from pylatexenc.latexwalker import (
    LatexEnvironmentNode,
    LatexGroupNode,
    LatexMacroNode,
    LatexWalker,
    get_default_latex_context_db,
)
from pylatexenc.macrospec import MacroSpec


class MainFileError(ValueError):
    pass


class MainFileNotFoundError(MainFileError):
    pass


class MultipleMainFilesError(MainFileError):
    pass


def _latex_context():
    # Add the class argument needed for reliable detection
    context = get_default_latex_context_db()
    context.add_context_category(
        "a11y-main-file",
        macros=[MacroSpec("documentclass", "[{")],
        prepend=True,
    )
    return context


def _group_text(node: LatexGroupNode | None) -> str:
    # Read the contents of a parsed argument group
    if node is None:
        return ""
    text = node.latex_verbatim()
    if len(text) >= 2 and text[0] == "{" and text[-1] == "}":
        return text[1:-1].strip()
    return text.strip()


def _walk_nodes(nodes: list) -> Iterator:
    # Visit parsed nodes and their nested content
    for node in nodes:
        yield node
        if isinstance(node, LatexEnvironmentNode) or isinstance(node, LatexGroupNode):
            yield from _walk_nodes(node.nodelist)
        if isinstance(node, LatexMacroNode) and node.nodeargd is not None:
            for argument in node.nodeargd.argnlist:
                if isinstance(argument, LatexGroupNode):
                    yield from _walk_nodes(argument.nodelist)


def is_beamer_main_file(path: Path) -> bool:
    # Check for a Beamer class and document environment
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    walker = LatexWalker(text, latex_context=_latex_context(), tolerant_parsing=True)
    nodes, _, _ = walker.get_latex_nodes()
    has_beamer_class = False
    has_document = False
    for node in _walk_nodes(nodes):
        if isinstance(node, LatexMacroNode) and node.macroname == "documentclass":
            arguments = node.nodeargd.argnlist
            if len(arguments) > 1 and _group_text(arguments[1]) == "beamer":
                has_beamer_class = True
        if isinstance(node, LatexEnvironmentNode) and node.environmentname == "document":
            has_document = True
    return has_beamer_class and has_document


PPTX_SUFFIX = ".pptx"
DOCX_SUFFIX = ".docx"
# Office files the pipeline reads directly: PowerPoint decks and Word documents
OFFICE_SUFFIXES = (PPTX_SUFFIX, DOCX_SUFFIX)
OFFICE_NAMES = {PPTX_SUFFIX: "PowerPoint (.pptx) deck", DOCX_SUFFIX: "Word (.docx) document"}


def is_office_main_file(path: Path) -> bool:
    # A deck or Word document is an OOXML zip; ignore Office's "~$" lock files
    return (
        path.suffix.lower() in OFFICE_SUFFIXES
        and not path.name.startswith("~$")
        and path.is_file()
        and zipfile.is_zipfile(path)
    )


def _validated_override(root: Path, main_file: str) -> str:
    # Validate an explicitly selected main source
    root_resolved = root.resolve()
    candidate = (root / main_file).resolve()
    if not candidate.is_relative_to(root_resolved):
        raise MainFileError(f"Main file escapes the bundle root: {main_file}")
    if not candidate.is_file():
        raise MainFileNotFoundError(f"Main file does not exist: {main_file}")
    suffix = candidate.suffix.lower()
    if suffix in OFFICE_SUFFIXES:
        if not is_office_main_file(candidate):
            raise MainFileNotFoundError(f"File is not a {OFFICE_NAMES[suffix]}: {main_file}")
    elif not is_beamer_main_file(candidate):
        raise MainFileNotFoundError(f"File is not a Beamer main file: {main_file}")
    return candidate.relative_to(root_resolved).as_posix()


def list_beamer_main_files(root: Path) -> list[str]:
    # List every Beamer entry point in a bundle, sorted by path
    candidates: list[str] = []
    for path in sorted(root.rglob("*.tex")):
        if path.is_file() and is_beamer_main_file(path):
            candidates.append(path.relative_to(root).as_posix())
    return candidates


def list_office_main_files(root: Path) -> list[str]:
    # List every PowerPoint deck and Word document in a bundle, sorted by path
    return [
        path.relative_to(root).as_posix()
        for path in sorted(root.rglob("*"))
        if "__MACOSX" not in path.parts and is_office_main_file(path)
    ]


def list_main_files(root: Path) -> list[str]:
    # Every translatable entry point: Beamer sources, PowerPoint decks and Word documents
    return sorted([*list_beamer_main_files(root), *list_office_main_files(root)])


def find_main_file(root: Path, main_file: str | None = None) -> str:
    # Find the only entry point (Beamer source, PowerPoint deck or Word document) in a bundle
    if not root.is_dir():
        raise MainFileNotFoundError(f"Bundle root is not a directory: {root}")
    if main_file is not None:
        return _validated_override(root, main_file)

    candidates = list_main_files(root)
    if not candidates:
        raise MainFileNotFoundError("No Beamer main file, PowerPoint deck or Word document found")
    if len(candidates) > 1:
        names = ", ".join(candidates)
        raise MultipleMainFilesError(f"Several main files found: {names}")
    return candidates[0]
