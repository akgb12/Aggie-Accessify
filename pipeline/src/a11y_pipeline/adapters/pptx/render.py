import os
import shutil
import subprocess
from pathlib import Path

MAC_APP_PATH = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
RENDER_TIMEOUT_SECONDS = 180
# Hidden slides are skipped by default, which would shift every later page off its slide
PDF_FILTER = 'pdf:impress_pdf_Export:{"ExportHiddenSlides":{"type":"boolean","value":"true"}}'


def find_soffice() -> str | None:
    # LibreOffice is the only renderer used; it is optional and found on PATH or in /Applications
    configured = os.environ.get("SOFFICE_PATH", "").strip()
    for candidate in (configured, shutil.which("soffice") or "", MAC_APP_PATH):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def render_deck_pdf(deck: Path, output_dir: Path) -> Path | None:
    # Render a deck to PDF so figures that are not plain pictures can be cropped for the model
    soffice = find_soffice()
    if soffice is None:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    profile = output_dir / "lo-profile"
    command = [
        soffice,
        f"-env:UserInstallation=file://{profile}",
        "--headless",
        "--convert-to",
        PDF_FILTER,
        "--outdir",
        str(output_dir),
        str(deck),
    ]
    try:
        subprocess.run(
            command,
            capture_output=True,
            check=True,
            timeout=RENDER_TIMEOUT_SECONDS,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    pdf = output_dir / f"{deck.stem}.pdf"
    return pdf if pdf.is_file() else None
