import re

GREEK_LETTERS = {
    "α": "alpha",
    "β": "beta",
    "γ": "gamma",
    "δ": "delta",
    "ε": "epsilon",
    "θ": "theta",
    "λ": "lambda",
    "μ": "mu",
    "π": "pi",
    "ρ": "rho",
    "σ": "sigma",
    "τ": "tau",
    "φ": "phi",
    "ω": "omega",
    "Δ": "delta",
    "Σ": "sigma",
    "Ω": "omega",
}

# Macros that only decorate the letter they wrap, spoken after it ("y hat")
ACCENT_MACROS = ("hat", "bar", "tilde", "dot", "vec")
# Macros that draw nothing a reader would say
SILENT_MACROS = (
    "cdots",
    "ldots",
    "dots",
    "quad",
    "qquad",
    "left",
    "right",
    "mathbf",
    "mathrm",
    "boldsymbol",
    "text",
)

MIN_FOLDED_LENGTH = 2


def has_math_markup(value: str) -> bool:
    # Tell a TeX math label from plain text
    return any(mark in value for mark in ("$", "\\", "_", "^"))


def fold_math(value: str) -> str:
    # Reduce text or a TeX math label to lowercase letters and digits so "$X_1$" equals "X1"
    text = value
    for letter, name in GREEK_LETTERS.items():
        text = text.replace(letter, f" {name} ")
    for macro in ACCENT_MACROS:
        text = re.sub(rf"\\{macro}\s*\{{([^{{}}]*)\}}", r"\1 " + macro, text)
        text = re.sub(rf"\\{macro}\s+([A-Za-z])", r"\1 " + macro, text)
    for macro in SILENT_MACROS:
        text = re.sub(rf"\\{macro}(?![A-Za-z])", " ", text)
    text = re.sub(r"\\([A-Za-z]+)", r" \1 ", text)
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def math_label_present(text: str, label: str) -> bool:
    # A math label counts as present when its folded form appears in the folded text
    if not has_math_markup(label):
        return False
    folded_label = fold_math(label)
    if len(folded_label) < MIN_FOLDED_LENGTH:
        return False
    return folded_label in fold_math(text)
