#!/usr/bin/env python3
"""
stamp_pdf.py — Add a scoring stamp to the bottom-right corner of every page in a PDF.

Usage:
    python3 stamp_pdf.py input.pdf [output.pdf]

If output.pdf is omitted, the stamped file is saved as input_stamped.pdf.
"""

import sys
import io
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from pypdf import PdfReader, PdfWriter


STAMP_LINES = [
    "DQ __________",
    "NS __________",
    "DFS __________",
]

# Pink — RGB 255, 105, 180 (hot pink, visible on white)
STAMP_COLOR = colors.HexColor("#FF69B4")
FONT_NAME = "Helvetica-Bold"
STAMP_WIDTH = 1.5 * 72  # 1.5 inches in points (108 pt)
MARGIN = 18  # points from right/bottom edge


def build_stamp(page_width: float, page_height: float) -> io.BytesIO:
    """Render the stamp overlay for a single page and return it as a PDF byte stream."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))

    # Scale font so the widest line is exactly STAMP_WIDTH
    font_size = STAMP_WIDTH / max(c.stringWidth(line, FONT_NAME, 1.0) for line in STAMP_LINES)
    line_height = font_size * 1.4

    c.setFont(FONT_NAME, font_size)
    c.setFillColor(STAMP_COLOR)

    x = page_width - MARGIN - STAMP_WIDTH
    # Draw lines bottom-up
    for i, line in enumerate(reversed(STAMP_LINES)):
        y = MARGIN + i * line_height
        c.drawString(x, y, line)

    c.save()
    buf.seek(0)
    return buf


def stamp_pdf(input_path: str, output_path: str) -> None:
    reader = PdfReader(input_path)
    writer = PdfWriter()

    for page in reader.pages:
        # Page dimensions (points)
        box = page.mediabox
        width = float(box.width)
        height = float(box.height)

        # Build a stamp PDF the same size as this page
        stamp_buf = build_stamp(width, height)
        stamp_page = PdfReader(stamp_buf).pages[0]

        # Merge stamp on top of the original page
        page.merge_page(stamp_page)
        writer.add_page(page)

    with open(output_path, "wb") as f:
        writer.write(f)

    print(f"Stamped PDF written to: {output_path}")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
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
