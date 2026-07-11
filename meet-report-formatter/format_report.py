#!/usr/bin/env python3
# requires Python 3.9+
"""
format_report.py — Erase the host-team label on every page of a HY-TEK Meet
Manager report PDF.

Meet Manager prints the host team's name as the leftmost text on the header
line of every page (e.g. "HY-TEK's MEET MANAGER 7.0 - 7/10/2026  Page 1
Chehalem Swim Team"). This tool finds that text run — identified by its
position, not its content, so it works regardless of which team is printed —
and blanks it.

Usage:
    python3 format_report.py input.pdf [output.pdf]

If output.pdf is omitted, the result is saved as input_formatted.pdf.

Note: replacing the label with a different team name (rather than erasing
it) is not yet supported. Meet Manager embeds subsetted fonts that only
contain the glyphs used elsewhere on the page, so writing arbitrary
replacement text through the same content stream can render missing/broken
glyphs. See README.md for details.
"""

import sys
import os
import math
import tempfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream, NameObject, TextStringObject

# Meet Manager's left page margin, in points. The host-team label is the
# first text run whose effective x-position lands at (or very near) this
# margin on the header line — this is what identifies it, not its content.
LEFT_MARGIN_X = 18.0
POSITION_TOLERANCE = 2.0

# The header line (containing "MEET MANAGER ... Page N") sits within ~60pt
# of the top of the page. Meet Manager exports have been observed using both
# a flipped coordinate system (Tm/cm with a -1 y-scale, so y near 0 is the
# top) and standard PDF coordinates (y near page height is the top) — so
# "near the top" is checked in both directions rather than assuming one.
HEADER_BAND = 60.0

# Some Meet Manager exports draw the team name and the "Page N" text as one
# TJ array, separated by a large horizontal jump (encoded as a kerning
# number) instead of as two separate text-positioning operators. Normal
# inter-glyph kerning in observed real-world output stays under ~150; a gap
# this large only occurs at a deliberate tab-like jump.
LARGE_GAP_THRESHOLD = 1000

# Safety limits
MAX_INPUT_BYTES = 100 * 1024 * 1024  # 100 MB — limits decompression bomb exposure
MAX_PAGES = 5_000                    # limits unbounded memory growth


def _near_top(y: float, page_height: float) -> bool:
    """True if y is within HEADER_BAND of the top of the page, in either
    a flipped (top ≈ 0) or standard (top ≈ page_height) coordinate system."""
    return y <= HEADER_BAND or y >= page_height - HEADER_BAND


def _blank_text_operand(operands):
    """Replace all string operands in a Tj/TJ operand list with empty strings."""
    if not operands:
        return
    first = operands[0]
    if isinstance(first, list):
        # TJ: [[str, num, str, num, ...]] — clear the array entirely
        first.clear()
    else:
        # Tj: [str]
        operands[0] = TextStringObject("")


def _blank_leading_run(tj_array):
    """
    Blank only the leading portion of a TJ array, up to (not including) the
    first large horizontal-jump number — used when the team name and the
    "Page N" text are packed into a single TJ operator rather than drawn as
    separate text-positioning operators.

    Returns True if a large gap was found and the leading run was blanked.
    """
    for i, item in enumerate(tj_array):
        if isinstance(item, (int, float)) and abs(float(item)) >= LARGE_GAP_THRESHOLD:
            for j in range(i):
                if isinstance(tj_array[j], str):
                    tj_array[j] = TextStringObject("")
            return True
    return False


def _edit_page_header(reader, page):
    """
    Rewrite the page's content stream, blanking the text run that starts at
    the left margin on the header line.

    Returns True if a matching run was found and edited.
    """
    cs = ContentStream(page["/Contents"], reader)
    ops = cs.operations

    box = page.mediabox
    page_height = float(box.height)

    cursor_x, cursor_y = None, None
    edited = False

    for operands, operator in ops:
        if operator == b"Tm" and len(operands) == 6:
            cursor_x, cursor_y = float(operands[4]), float(operands[5])
        elif operator in (b"Td", b"TD") and len(operands) == 2:
            dx, dy = float(operands[0]), float(operands[1])
            if cursor_x is None:
                cursor_x, cursor_y = dx, dy
            else:
                cursor_x += dx
                cursor_y += dy
        elif operator in (b"Tj", b"TJ"):
            if (
                cursor_x is not None
                and cursor_y is not None
                and abs(cursor_x - LEFT_MARGIN_X) <= POSITION_TOLERANCE
                and _near_top(cursor_y, page_height)
            ):
                first = operands[0] if operands else None
                if operator == b"TJ" and isinstance(first, list) and _blank_leading_run(first):
                    edited = True
                else:
                    _blank_text_operand(operands)
                    edited = True

    if edited:
        page[NameObject("/Contents")] = cs

    return edited


def format_report(input_path: str, output_path: str) -> None:
    """Erase the host-team label on every page of input_path."""
    src = Path(input_path)

    if src.suffix.lower() != ".pdf":
        raise ValueError(f"Input must be a .pdf file, got: {src.suffix!r}")

    if not src.is_file():
        raise FileNotFoundError(f"Not a regular file: {src}")

    file_size = src.stat().st_size
    if file_size > MAX_INPUT_BYTES:
        raise ValueError(
            f"Input file too large: {file_size:,} bytes (limit {MAX_INPUT_BYTES:,})"
        )

    reader = PdfReader(str(src))

    if len(reader.pages) > MAX_PAGES:
        raise ValueError(
            f"PDF has too many pages: {len(reader.pages):,} (limit {MAX_PAGES:,})"
        )

    writer = PdfWriter()
    pages_edited = 0

    for page in reader.pages:
        box = page.mediabox
        width, height = float(box.width), float(box.height)
        if not (math.isfinite(width) and math.isfinite(height)
                and width > 0 and height > 0):
            raise ValueError(f"Invalid page dimensions: {width} x {height}")

        if _edit_page_header(reader, page):
            pages_edited += 1

        writer.add_page(page)

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
    print(f"Team label erased on {pages_edited}/{len(reader.pages)} pages. "
          f"Output written to: {output_path!r}")


def main() -> None:
    """Parse CLI arguments and invoke format_report."""
    args = sys.argv[1:]

    if "--help" in args or not args:
        print(__doc__)
        sys.exit(0 if args else 1)

    if "--replace" in args:
        print(
            "Error: --replace is not yet supported. Meet Manager embeds "
            "subsetted fonts (only the glyphs used elsewhere on the page "
            "are present), so writing arbitrary replacement text can "
            "render missing/broken glyphs. Use erase mode (omit --replace) "
            "for now — see README.md."
        )
        sys.exit(1)

    input_path = args[0]
    output_path = args[1] if len(args) >= 2 else str(
        Path(input_path).with_stem(Path(input_path).stem + "_formatted")
    )

    format_report(input_path, output_path)


if __name__ == "__main__":
    main()
