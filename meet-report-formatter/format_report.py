#!/usr/bin/env python3
# requires Python 3.9+
"""
format_report.py — Erase the host-team label on every page of a HY-TEK Meet
Manager report PDF.

Meet Manager prints the host team's name as the leftmost text on the header
line of every page (e.g. "HY-TEK's MEET MANAGER 7.0 - 7/10/2026  Page 1
Example Swim Team"). This tool finds that text run — identified by its
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
from pypdf.generic import ContentStream, FloatObject, NameObject, TextStringObject

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
    a flipped (top ≈ 0) or standard (top ≈ page_height) coordinate system.

    Both bounds are checked on each branch — not just an upper/lower bound
    in isolation — because a Td chain deep in the page body can drift back
    to a small (or even negative) y that satisfies an unbounded "y <= band"
    check without the text actually being anywhere near the top of the
    page. Requiring y to fall inside [0, page_height] first rules that out.
    """
    return (0 <= y <= HEADER_BAND) or (page_height - HEADER_BAND <= y <= page_height)


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


def _font_widths(page, font_name):
    """
    Return (widths_list, first_char, default_width) for the simple font
    named font_name in page's /Font resources, or None if it can't be
    read as a simple font with a /Widths array (e.g. a /Type0 CID font).
    """
    if font_name is None:
        return None
    try:
        font = page["/Resources"]["/Font"][font_name].get_object()
    except KeyError:
        return None
    widths = font.get("/Widths")
    first_char = font.get("/FirstChar")
    if widths is None or first_char is None:
        return None
    descriptor = font.get("/FontDescriptor")
    default_width = 0
    if descriptor is not None:
        default_width = descriptor.get_object().get("/MissingWidth", 0)
    return [float(w) for w in widths], int(first_char), float(default_width)


def _glyph_run_width(text, font_metrics, font_size, char_spacing, word_spacing):
    """
    Text-space width (in points) that Meet Manager's own renderer would have
    consumed drawing `text` at font_size with the given /Tc and /Tw — i.e.
    the horizontal distance the erased glyphs were "budgeted" for. ASCII
    text only: character codes are taken as ord(char), which matches both
    WinAnsiEncoding and the implicit standard encoding used by these fonts
    in the printable-ASCII range that team names fall in.
    """
    widths, first_char, default_width = font_metrics
    total = 0.0
    for ch in text:
        code = ord(ch)
        idx = code - first_char
        glyph_width = widths[idx] if 0 <= idx < len(widths) else default_width
        total += glyph_width / 1000.0 * font_size + char_spacing
        if code == 32:
            total += word_spacing
    return total


def _blank_leading_run(tj_array, font_metrics, font_size, char_spacing, word_spacing):
    """
    Blank only the leading portion of a TJ array, up to (not including) the
    first large horizontal-jump number — used when the team name and the
    "Page N" text are packed into a single TJ operator rather than drawn as
    separate text-positioning operators.

    Blanking a glyph run removes its contribution to the pen's horizontal
    advance (the run's own character widths no longer apply), which would
    otherwise pull everything after it — "HY-TEK's MEET MANAGER... Page N"
    — left out of its original right-justified position. To keep it in
    place, the removed run's total advance width is folded into a single
    compensating kerning number spliced in where the run used to be, so the
    pen ends up exactly where it would have after the original glyphs drew.

    Returns True if a large gap was found and the leading run was blanked.
    """
    for i, item in enumerate(tj_array):
        if isinstance(item, (int, float)) and abs(float(item)) >= LARGE_GAP_THRESHOLD:
            removed_width = 0.0
            for j in range(i):
                if isinstance(tj_array[j], str):
                    if font_metrics is not None:
                        removed_width += _glyph_run_width(
                            tj_array[j], font_metrics, font_size,
                            char_spacing, word_spacing,
                        )
                    tj_array[j] = TextStringObject("")
            if removed_width and font_size:
                # A TJ number n shifts the pen by -n/1000*font_size, i.e. a
                # *smaller* (more negative) number advances the pen further
                # right. Erasing the run's glyphs drops their rightward
                # advance, so the gap number must shrink by the same amount
                # to keep the pen landing in the same place.
                tj_array[i] = FloatObject(
                    float(tj_array[i]) - removed_width / font_size * 1000.0
                )
            return True
    return False


class _TextState:
    """Tracks the subset of PDF text-positioning/font state needed to find
    the header run and, if it's a packed TJ array, compute glyph widths for
    the compensating kerning gap: cursor position, current font, and the
    /Tc, /Tw spacing parameters that feed into glyph advance."""

    def __init__(self):
        self.cursor_x = None
        self.cursor_y = None
        self.font_name = None
        self.font_size = None
        self.char_spacing = 0.0
        self.word_spacing = 0.0

    def update(self, operator, operands):
        """Apply one content-stream operator's effect on cursor/font state."""
        if operator == b"Tm" and len(operands) == 6:
            self.cursor_x, self.cursor_y = float(operands[4]), float(operands[5])
        elif operator in (b"Td", b"TD") and len(operands) == 2:
            dx, dy = float(operands[0]), float(operands[1])
            if self.cursor_x is None:
                self.cursor_x, self.cursor_y = dx, dy
            else:
                self.cursor_x += dx
                self.cursor_y += dy
        elif operator == b"Tf" and len(operands) == 2:
            self.font_name, self.font_size = operands[0], float(operands[1])
        elif operator == b"Tc" and len(operands) == 1:
            self.char_spacing = float(operands[0])
        elif operator == b"Tw" and len(operands) == 1:
            self.word_spacing = float(operands[0])

    def at_header_position(self, page_height):
        """True if the cursor is at the left margin, near the top of the page."""
        return (
            self.cursor_x is not None
            and self.cursor_y is not None
            and abs(self.cursor_x - LEFT_MARGIN_X) <= POSITION_TOLERANCE
            and _near_top(self.cursor_y, page_height)
        )


def _blank_header_run(operator, operands, page, state):
    """Blank a Tj/TJ operator's text at the header position, compensating
    for lost glyph-advance width if it's a packed TJ array with a gap."""
    first = operands[0] if operands else None
    found_gap = False
    if operator == b"TJ" and isinstance(first, list):
        font_metrics = _font_widths(page, state.font_name)
        found_gap = _blank_leading_run(
            first, font_metrics, state.font_size, state.char_spacing, state.word_spacing
        )
    if not found_gap:
        _blank_text_operand(operands)


def _edit_page_header(reader, page):
    """
    Rewrite the page's content stream, blanking the text run that starts at
    the left margin on the header line.

    Returns True if a matching run was found and edited.
    """
    cs = ContentStream(page["/Contents"], reader)
    page_height = float(page.mediabox.height)

    state = _TextState()
    edited = False

    for operands, operator in cs.operations:
        if operator in (b"Tj", b"TJ"):
            if state.at_header_position(page_height):
                _blank_header_run(operator, operands, page, state)
                edited = True
        else:
            state.update(operator, operands)

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
