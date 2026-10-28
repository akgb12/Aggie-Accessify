from a11y_pipeline.ir.models import DocumentIR, Element


def figure_context(ir: DocumentIR, figure: Element) -> tuple[str | None, list[str]]:
    # Gather the slide title and nearby visible text
    container_id = figure.id.split("/", 1)[0]
    slide_title = None
    nearby: list[str] = []
    container = None
    for candidate in ir.containers:
        if candidate.id == container_id:
            container = candidate
            break
    if container is not None and container.title_element_id is not None:
        title = ir.elements.get(container.title_element_id)
        if title is not None:
            slide_title = element_text(title)
    prefix = f"{container_id}/"
    for element in ir.elements.values():
        if not element.id.startswith(prefix):
            continue
        if element.id == figure.id or element.semantic_type in {"figure", "heading"}:
            continue
        text = element_text(element)
        if text:
            nearby.append(text)
    return slide_title, nearby


def element_text(element: Element) -> str | None:
    # Read plain visible text from one element
    text = element.content.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return None
