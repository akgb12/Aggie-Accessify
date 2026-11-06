from pydantic import BaseModel, ConfigDict

from a11y_pipeline.ir.models import DocumentIR


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    element_id: str
    capability: str
    reason: str


def analyze_needs(document: DocumentIR) -> list[Task]:
    # Find elements that need semantic model work
    tasks: list[Task] = []
    for element in document.elements.values():
        accessibility = element.accessibility
        if element.semantic_type == "heading" and element.attrs.get("added_title"):
            if accessibility.status == "needs_description" and not accessibility.locked:
                tasks.append(
                    Task(
                        element_id=element.id,
                        capability="slide_title",
                        reason="Slide has no title",
                    )
                )
            continue
        if element.subtype == "document_outline":
            if accessibility.status == "needs_description" and not accessibility.locked:
                tasks.append(
                    Task(
                        element_id=element.id,
                        capability="document_outline",
                        reason="Document headings, languages or title need deciding",
                    )
                )
            continue
        if element.semantic_type != "figure":
            continue
        if accessibility.status != "needs_description":
            continue
        if accessibility.locked:
            continue
        tasks.append(
            Task(
                element_id=element.id,
                capability="figure_description",
                reason="Figure needs an accessibility description",
            )
        )
    return tasks
