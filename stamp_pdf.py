#!/usr/bin/env python3
# requires Python 3.9+
"""
stamp_pdf.py — Add a scoring stamp to the bottom-right corner of every page in a PDF.

Usage:
    python3 stamp_pdf.py input.pdf [output.pdf]

If output.pdf is omitted, the stamped file is saved as input_stamped.pdf.
"""

import sys
import io
import functools
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from pypdf import PdfReader, PdfWriter


STAMP_LINES = (
    "DQ __________",
    "NS __________",
    "DFS __________",
)

# Pink — RGB 255, 105, 180 (hot pink, visible on white)
STAMP_COLOR = colors.HexColor("#FF69B4")
FONT_NAME = "Helvetica-Bold"
STAMP_WIDTH = 1.5 * 72  # 1.5 inches in points (108 pt)
MARGIN = 18  # points from right/bottom edge

# Font metrics are constant — compute once at module load, not per page
_FONT_SIZE = STAMP_WIDTH / max(pdfmetrics.stringWidth(line, FONT_NAME, 1.0) for line in STAMP_LINES)
_LINE_HEIGHT = _FONT_SIZE * 1.4


@functools.lru_cache(maxsize=8)
def _stamp_bytes(page_width: float, page_height: float) -> bytes:
    """Build the stamp overlay as raw PDF bytes for a given page size (cached)."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))
    c.setFont(FONT_NAME, _FONT_SIZE)
    c.setFillColor(STAMP_COLOR)
    x = page_width - MARGIN - STAMP_WIDTH
    for i, line in enumerate(reversed(STAMP_LINES)):
        y = MARGIN + i * _LINE_HEIGHT
        c.drawString(x, y, line)
    c.save()
    return buf.getvalue()


def build_stamp(page_width: float, page_height: float) -> io.BytesIO:
    """Return the stamp overlay for a single page as a fresh BytesIO PDF stream."""
    return io.BytesIO(_stamp_bytes(page_width, page_height))


def stamp_pdf(input_path: str, output_path: str) -> None:
    reader = PdfReader(input_path)
    writer = PdfWriter()

    for page in reader.pages:
        # Page dimensions (points)
        box = page.mediabox
        width = float(box.width)
        height = float(box.height)

        # Add page to writer first — required before merge_page in pypdf ≥6
        added = writer.add_page(page)
        stamp_page = PdfReader(build_stamp(width, height)).pages[0]
        added.merge_page(stamp_page)

    with open(output_path, "wb") as f:
        writer.write(f)

    print(f"Stamped PDF written to: {output_path}")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__ or "Usage: stamp_pdf.py input.pdf [output.pdf]")
        sys.exit(1)

    input_path = sys.argv[1]
    if len(sys.argv) >= 3:
        output_path = sys.argv[2]
    else:
        p = Path(input_path)
        output_path = str(p.with_stem(p.stem + "_stamped"))

    stamp_pdf(input_path, output_path)


if __name__ == "__main__":
    main()
