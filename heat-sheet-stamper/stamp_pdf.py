#!/usr/bin/env python3
# requires Python 3.9+
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Adam Sealey

"""
stamp_pdf.py — Add a scoring stamp to the bottom-right corner of every page in a PDF.

Usage:
    python3 stamp_pdf.py [--sr | --dr | --auto] input.pdf [output.pdf]

Flags:
    --sr    Add "SR" to the top-right corner only (no bottom-right stamp)
    --dr    Add "DR" to the top-right corner and the DQ/NS/DFS bottom-right stamp
    --auto  Produce both: input-sr.pdf and input-dr.pdf in one pass

If output.pdf is omitted, the stamped file is saved as input_stamped.pdf.
"""

import sys
import io
import math
import os
import functools
import tempfile
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter


STAMP_LINES = (
    "DQ ___________",
    "NS ___________",
    "DFS __________",
)

# Pink — RGB 255, 105, 180 (hot pink, visible on white)
STAMP_COLOR = colors.HexColor("#FF69B4")

# Andale Mono is a clean, modern monospace font; fall back to Courier-Bold if unavailable
_ANDALE_MONO_PATH = "/System/Library/Fonts/Supplemental/Andale Mono.ttf"
try:
    pdfmetrics.registerFont(TTFont("AndaleMono", _ANDALE_MONO_PATH))
    FONT_NAME = "AndaleMono"
except Exception:  # pylint: disable=broad-exception-caught
    FONT_NAME = "Courier-Bold"
STAMP_WIDTH = 1.5 * 72  # 1.5 inches in points (108 pt)
MARGIN = 18  # points from right/bottom edge
STAMP_FONT_NAME = "Helvetica-Bold"  # bold PDF built-in for the bottom-right stamp

# Safety limits
MAX_INPUT_BYTES = 100 * 1024 * 1024  # 100 MB — limits decompression bomb exposure
MAX_PAGES = 5_000                    # limits unbounded memory growth

CORNER_LABEL_SIZE = 25  # points — 36 * 0.7, reduced 30% from original

# Font metrics are constant — compute once at module load, not per page
_FONT_SIZE = STAMP_WIDTH / max(
    pdfmetrics.stringWidth(line, STAMP_FONT_NAME, 1.0) for line in STAMP_LINES
)
_LINE_HEIGHT = _FONT_SIZE * 1.4


@functools.lru_cache(maxsize=8)
def _stamp_bytes(page_width: float, page_height: float) -> bytes:
    """Build the bottom-right stamp overlay as raw PDF bytes (cached)."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))
    c.setFont(STAMP_FONT_NAME, _FONT_SIZE)
    c.setFillColor(STAMP_COLOR)
    x = page_width - MARGIN - STAMP_WIDTH
    for i, line in enumerate(reversed(STAMP_LINES)):
        y = MARGIN + i * _LINE_HEIGHT
        c.drawString(x, y, line)
    c.save()
    return buf.getvalue()


@functools.lru_cache(maxsize=16)
def _corner_label_bytes(label: str, page_width: float, page_height: float) -> bytes:
    """Build a top-right corner label overlay as raw PDF bytes (cached)."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))
    c.setFont(FONT_NAME, CORNER_LABEL_SIZE)
    c.setFillColor(STAMP_COLOR)
    text_width = pdfmetrics.stringWidth(label, FONT_NAME, CORNER_LABEL_SIZE)
    x = page_width - MARGIN - text_width
    y = page_height - MARGIN - CORNER_LABEL_SIZE
    c.drawString(x, y, label)
    c.save()
    return buf.getvalue()


def build_stamp(page_width: float, page_height: float) -> io.BytesIO:
    """Return the bottom-right stamp overlay as a fresh BytesIO PDF stream."""
    return io.BytesIO(_stamp_bytes(page_width, page_height))


def build_corner_label(label: str, page_width: float, page_height: float) -> io.BytesIO:
    """Return a top-right corner label overlay as a fresh BytesIO PDF stream."""
    return io.BytesIO(_corner_label_bytes(label, page_width, page_height))


def stamp_pdf(
    input_path: str,
    output_path: str,
    *,
    corner_label: str = "",
    include_stamp: bool = True,
) -> None:
    """Overlay scoring stamps onto input_path and write the result to output_path."""
    # pylint: disable=too-many-locals
    src = Path(input_path)

    # Reject non-PDF extensions
    if src.suffix.lower() != ".pdf":
        raise ValueError(f"Input must be a .pdf file, got: {src.suffix!r}")

    # Reject non-regular files (device files, named pipes, /dev/zero, etc.)
    if not src.is_file():
        raise FileNotFoundError(f"Not a regular file: {src}")

    # Limit input size to reduce decompression bomb exposure
    file_size = src.stat().st_size
    if file_size > MAX_INPUT_BYTES:
        raise ValueError(
            f"Input file too large: {file_size:,} bytes (limit {MAX_INPUT_BYTES:,})"
        )

    reader = PdfReader(str(src))

    # Limit page count to prevent unbounded memory growth
    if len(reader.pages) > MAX_PAGES:
        raise ValueError(
            f"PDF has too many pages: {len(reader.pages):,} (limit {MAX_PAGES:,})"
        )

    writer = PdfWriter()

    for page in reader.pages:
        box = page.mediabox
        width = float(box.width)
        height = float(box.height)

        # Reject NaN/Inf/non-positive dimensions from malformed PDFs
        if not (math.isfinite(width) and math.isfinite(height)
                and width > 0 and height > 0):
            raise ValueError(f"Invalid page dimensions: {width} x {height}")

        # Add page to writer first — required before merge_page in pypdf ≥6
        added = writer.add_page(page)

        if include_stamp:
            added.merge_page(PdfReader(build_stamp(width, height)).pages[0])

        if corner_label:
            added.merge_page(
                PdfReader(build_corner_label(corner_label, width, height)).pages[0]
            )

    # Write atomically: write to a temp file in the same directory, then
    # rename into place. os.replace() swaps the directory entry rather than
    # following symlinks, so this also prevents symlink-following writes.
    out = Path(output_path)
    tmp_fd, tmp_name = tempfile.mkstemp(dir=out.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            writer.write(f)
        os.replace(tmp_name, output_path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise

    # !r escapes control characters, preventing terminal escape injection
    print(f"Stamped PDF written to: {output_path!r}")


def main() -> None:
    """Parse CLI arguments and invoke stamp_pdf."""
    args = sys.argv[1:]

    if "--help" in args:
        print(__doc__ or "Usage: stamp_pdf.py [--sr | --dr | --auto] input.pdf [output.pdf]")
        sys.exit(0)

    has_sr = "--sr" in args
    has_dr = "--dr" in args
    has_auto = "--auto" in args

    if (has_sr + has_dr + has_auto) > 1:
        print("Error: --sr, --dr, and --auto are mutually exclusive.")
        sys.exit(1)

    if has_auto:
        args = [a for a in args if a != "--auto"]
        if not args:
            print(__doc__ or "Usage: stamp_pdf.py [--sr | --dr | --auto] input.pdf [output.pdf]")
            sys.exit(1)
        input_path = args[0]
        parent = Path(input_path).parent
        stem = Path(input_path).stem
        stamp_pdf(input_path, str(parent / f"{stem}-sr.pdf"),
                  corner_label="SR", include_stamp=False)
        stamp_pdf(input_path, str(parent / f"{stem}-dr.pdf"),
                  corner_label="DR", include_stamp=True)
        return

    corner_label = ""
    include_stamp = True
    if has_sr:
        corner_label = "SR"
        include_stamp = False
        args = [a for a in args if a != "--sr"]
    elif has_dr:
        corner_label = "DR"
        include_stamp = True
        args = [a for a in args if a != "--dr"]

    if not args:
        print(__doc__ or "Usage: stamp_pdf.py [--sr | --dr | --auto] input.pdf [output.pdf]")
        sys.exit(1)

    input_path = args[0]
    output_path = args[1] if len(args) >= 2 else str(
        Path(input_path).with_stem(Path(input_path).stem + "_stamped")
    )

    stamp_pdf(input_path, output_path, corner_label=corner_label, include_stamp=include_stamp)


if __name__ == "__main__":
    main()
