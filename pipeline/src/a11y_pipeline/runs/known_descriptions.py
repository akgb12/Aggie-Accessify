from typing import Any, NamedTuple

from a11y_pipeline.ir.models import DocumentIR

# A deck or document can only hold one line of alt text per figure, so an update writes the
# short description and the long one together. Running the update again reads that line back
# as one long short description. Descriptions an earlier run wrote are recognised by their
# exact text and split again, so the file is judged as it was when that run made it.


class KnownDescription(NamedTuple):
    alt: str
    extended: str | None
    # The labels and terms the earlier run measured the description against. Its excluded
    # labels are left behind: they would let a figure read back without its labels reject
    # quotes of them, though the earlier run checked those quotes against the labels.
    required_concepts: list[str] = []


KnownDescriptions = dict[str, KnownDescription]


def description_key(alt: str, extended: str | None) -> str:
    # The text an update writes for a description, with whitespace evened out
    return " ".join(f"{alt} {extended or ''}".split())


def known_descriptions(ir_final: dict[str, Any]) -> KnownDescriptions:
    # The descriptions a finished run gave its figures, from its saved final document
    known: KnownDescriptions = {}
    for element in ir_final.get("elements", {}).values():
        if element.get("semantic_type") != "figure":
            continue
        accessibility = element.get("accessibility", {})
        alt = " ".join((accessibility.get("alt_text") or "").split())
        if not alt or accessibility.get("decorative"):
            continue
        extended = " ".join((accessibility.get("extended_description") or "").split()) or None
        fidelity = element.get("fidelity", {})
        known[description_key(alt, extended)] = KnownDescription(
            alt,
            extended,
            [str(concept) for concept in fidelity.get("required_concepts", [])],
        )
    return known


def restore_known_descriptions(document: DocumentIR, known: KnownDescriptions) -> int:
    # Split each figure description an earlier run wrote back into its short and long parts,
    # and measure it against the same terms that run used, so the same file scores the same;
    # returns how many were recognised. Text anyone has since changed is not recognised.
    restored = 0
    for element in document.elements.values():
        accessibility = element.accessibility
        if element.semantic_type != "figure" or not accessibility.alt_text:
            continue
        key = description_key(accessibility.alt_text, accessibility.extended_description)
        if key not in known:
            continue
        description = known[key]
        accessibility.alt_text, accessibility.extended_description = (
            description.alt,
            description.extended,
        )
        if not element.fidelity.required_concepts:
            element.fidelity.required_concepts = list(description.required_concepts)
        restored += 1
    return restored
