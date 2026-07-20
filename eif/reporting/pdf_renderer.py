"""EIF compliance report PDF renderer.

Converts the markdown string produced by eif_compliance_report into a
well-structured PDF suitable for auditors and compliance contractors.

Design:
  - Pure Python (fpdf2). No external binaries (wkhtmltopdf, pandoc, etc.).
  - Output path: ~/.eif/reports/eif_compliance_{session_id[:8]}_{YYYYMMDD_HHMMSS}.pdf
  - Graceful fallback: if fpdf2 is not installed, raises ImportError with
    install instructions. The MCP tool catches this and returns a helpful message.

Section rendering:
  - # H1  → large bold header, light blue rule
  - ## H2 → medium bold header, grey rule
  - **bold** text → detected inline and rendered bold
  - --- → horizontal divider
  - - bullet  → indented bullet point
  - plain text → body paragraph (auto word-wrap)

All font work uses the built-in Helvetica family (no font files needed).
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path

_REPORTS_DIR = Path(os.environ.get("EIF_REPORTS_DIR", Path.home() / ".eif" / "reports"))

# Characters outside latin-1 that appear in EIF reports → closest ASCII equivalent
_UNICODE_SUBS: dict[str, str] = {
    "\u2014": "--",   # em dash
    "\u2013": "-",    # en dash
    "\u2019": "'",    # right single quote
    "\u2018": "'",    # left single quote
    "\u201c": '"',    # left double quote
    "\u201d": '"',    # right double quote
    "\u2022": "-",    # bullet
    "\u2026": "...",  # ellipsis
    "\u00a0": " ",    # non-breaking space
    "\u2192": "->",   # right arrow
    "\u2190": "<-",   # left arrow
    "\u2713": "[OK]", # check mark
    "\u2717": "[X]",  # cross mark
    "\u26a0": "[!]",  # warning
}


def _safe(text: str) -> str:
    """Replace characters outside latin-1 with ASCII equivalents."""
    for char, replacement in _UNICODE_SUBS.items():
        text = text.replace(char, replacement)
    # Final pass: encode to latin-1, replacing anything still outside range
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _ensure_fpdf():
    try:
        from fpdf import FPDF  # fpdf2
        return FPDF
    except ImportError as exc:
        raise ImportError(
            "fpdf2 is required for PDF export. Install it with:\n"
            "  pip install fpdf2\n"
            "Or install EIF with the pdf extra:\n"
            "  pip install eif-engine[pdf]"
        ) from exc


def render_compliance_pdf(markdown: str, session_id: str) -> Path:
    """Render the given markdown compliance report to a PDF file.

    Returns the path to the written PDF.
    """
    FPDF = _ensure_fpdf()

    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    out_path = _REPORTS_DIR / f"eif_compliance_{session_id[:8]}_{ts}.pdf"

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # Page margins
    left_margin = 20
    right_margin = 20
    page_width = 210 - left_margin - right_margin  # A4 is 210mm wide
    pdf.set_left_margin(left_margin)
    pdf.set_right_margin(right_margin)

    def _rule(color: tuple = (200, 200, 200), height_mm: float = 0.3) -> None:
        pdf.set_draw_color(*color)
        pdf.set_line_width(height_mm)
        pdf.line(left_margin, pdf.get_y(), 210 - right_margin, pdf.get_y())
        pdf.ln(3)

    def _h1(text: str) -> None:
        pdf.set_font("Helvetica", style="B", size=18)
        pdf.set_text_color(20, 60, 120)
        pdf.multi_cell(0, 10, _safe(text))
        pdf.set_text_color(0, 0, 0)
        _rule(color=(20, 60, 120), height_mm=0.5)
        pdf.ln(2)

    def _h2(text: str) -> None:
        pdf.set_font("Helvetica", style="B", size=13)
        pdf.set_text_color(60, 60, 60)
        pdf.multi_cell(0, 8, _safe(text))
        pdf.set_text_color(0, 0, 0)
        _rule(color=(180, 180, 180), height_mm=0.2)
        pdf.ln(1)

    def _bullet(text: str) -> None:
        pdf.set_font("Helvetica", size=10)
        pdf.set_x(left_margin + 5)
        pdf.multi_cell(page_width - 5, 6, f"*  {_safe(text)}")

    def _body(text: str) -> None:
        """Render a line of body text. Handles **bold** inline markers."""
        parts = re.split(r"(\*\*[^*]+\*\*)", text)
        pdf.set_x(left_margin)
        has_bold = any(p.startswith("**") for p in parts)
        if not has_bold:
            pdf.set_font("Helvetica", size=10)
            pdf.multi_cell(0, 6, _safe(text))
            return
        # Write inline bold by switching font per segment
        for part in parts:
            if part.startswith("**") and part.endswith("**"):
                pdf.set_font("Helvetica", style="B", size=10)
                pdf.write(6, _safe(part[2:-2]))
            else:
                pdf.set_font("Helvetica", size=10)
                pdf.write(6, _safe(part))
        pdf.ln(6)

    def _divider() -> None:
        pdf.ln(2)
        _rule(color=(160, 160, 160), height_mm=0.2)
        pdf.ln(2)

    # ── Render markdown lines ─────────────────────────────────────────────────
    for raw_line in markdown.splitlines():
        line = raw_line.strip()

        if line.startswith("# "):
            _h1(line[2:])
        elif line.startswith("## "):
            _h2(line[3:])
        elif line.startswith("---"):
            _divider()
        elif line.startswith("- "):
            _bullet(line[2:])
        elif line == "":
            pdf.ln(3)
        else:
            _body(line)

    # Footer on every page
    pdf.set_y(-15)
    pdf.set_font("Helvetica", style="I", size=8)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 10, _safe(f"EIF Engine | Session {session_id[:8]} | {ts[:8]}"), align="C")

    pdf.output(str(out_path))
    return out_path
