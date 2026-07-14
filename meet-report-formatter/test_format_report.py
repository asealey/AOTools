"""
test_format_report.py — Test suite for format_report.py

Run with:
    pytest test_format_report.py -v
"""

import io
from pathlib import Path

import pymupdf
import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    ContentStream,
    DictionaryObject,
    NameObject,
    NumberObject,
)

from format_report import format_report


# ---------------------------------------------------------------------------
# Helpers — build a minimal PDF whose header line mimics Meet Manager's
# layout: an absolute Tm to the right (simulating "...Page N"), then a Td
# jump back to the left margin (x=18) to draw the team name, matching the
# real content-stream shape observed in HY-TEK Meet Manager 7.0 output.
# ---------------------------------------------------------------------------

def _make_header_content_stream(team_name: str, use_tm_for_team: bool = False) -> bytes:
    """
    Build raw PDF content-stream bytes with a two-part header line:
    "Page 1" drawn first (starting mid-page), then the team name drawn
    at the left margin — either via a relative Td jump (as in the
    multi-page team report) or an absolute Tm (as in the single-page
    team fee report). Both forms occur in real Meet Manager output.
    """
    lines = [
        "BT",
        "/F1 8.55 Tf",
        "1 0 0 -1 372 45.5 Tm",
        "(Page 1) Tj",
    ]
    if use_tm_for_team:
        lines.append("1 0 0 -1 18 45.5 Tm")
    else:
        lines.append("-354 0 Td")
    lines.append(f"({team_name}) Tj")
    lines.append("170.25 -12 Td")
    lines.append("(Body text below) Tj")
    lines.append("ET")
    return "\n".join(lines).encode("latin-1")


def make_meet_manager_pdf(team_name: str = "Example Swim Team",
                           num_pages: int = 1,
                           use_tm_for_team: bool = False) -> bytes:
    """Build a minimal PDF whose pages carry a Meet-Manager-shaped header."""
    writer = PdfWriter()
    for _ in range(num_pages):
        page = writer.add_blank_page(width=612, height=792)
        content = _make_header_content_stream(team_name, use_tm_for_team)

        # pypdf's PageObject doesn't expose a simple "set raw content stream"
        # helper across versions, so write the bytes directly.
        from pypdf.generic import StreamObject
        content_obj = StreamObject()
        content_obj.set_data(content)
        page[NameObject("/Contents")] = writer._add_object(content_obj)

        # Minimal font resource so viewers/extractors don't choke.
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({
                NameObject("/F1"): writer._add_object(font),
            })
        })

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def write_temp_pdf(data: bytes, tmp_path: Path, name: str = "input.pdf") -> Path:
    p = tmp_path / name
    p.write_bytes(data)
    return p


# ---------------------------------------------------------------------------
# Helper — build a minimal PDF whose header packs the team name and "Page N"
# into a single TJ array separated by a large kerning-style gap, matching
# the export shape seen in ngsl-invitational-2022.pdf and the OSAA reports
# (as opposed to the two-Tj-operator shape _make_header_content_stream
# above simulates). All glyphs are given a fixed 500/1000-em width via
# /Widths so the compensating-gap math can be checked exactly.
# ---------------------------------------------------------------------------

GLYPH_WIDTH = 500  # 1/1000 em, applied uniformly to FirstChar..LastChar below


def make_packed_tj_pdf(team_name: str, page_text: str = "Page 1") -> bytes:
    """Build a minimal PDF whose header is one TJ array:
    [team_name glyphs..., big_gap, page_text glyphs...], with a /Widths
    table so the erased run's advance width is computable in the test."""
    font_size = 10
    gap = -2000  # thousandths; well past LARGE_GAP_THRESHOLD
    tj_array = "".join(f"({ch})" for ch in team_name) + f" {gap} " + f"({page_text})"

    content = "\n".join([
        "BT",
        f"/F1 {font_size} Tf",
        "1 0 0 -1 18 45.5 Tm",
        f"[{tj_array}] TJ",
        "ET",
    ]).encode("latin-1")

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    from pypdf.generic import StreamObject
    content_obj = StreamObject()
    content_obj.set_data(content)
    page[NameObject("/Contents")] = writer._add_object(content_obj)

    num_chars = 128
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/TrueType"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
        NameObject("/FirstChar"): NumberObject(0),
        NameObject("/Widths"): ArrayObject(
            NumberObject(GLYPH_WIDTH) for _ in range(num_chars)
        ),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({
            NameObject("/F1"): writer._add_object(font),
        })
    })

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Packed-TJ-array header (team name and "Page N" in one TJ, separated by a
# large kerning gap) — the export shape where blanking glyphs without
# compensating for their lost advance width used to shift "Page N" left.
# ---------------------------------------------------------------------------

class TestPackedTjHeader:
    def test_page_text_survives_and_team_name_is_gone(self, tmp_path):
        pdf_bytes = make_packed_tj_pdf("Example Swim Team")
        src = write_temp_pdf(pdf_bytes, tmp_path)
        out = tmp_path / "out.pdf"

        format_report(str(src), str(out))

        text = PdfReader(str(out)).pages[0].extract_text()
        assert "Example" not in text
        assert "Page 1" in text

    def test_gap_number_compensates_exactly_for_removed_glyph_width(self, tmp_path):
        """The erased run was 17 glyphs at 500/1000 em, 10pt font — i.e. an
        85pt advance the pen no longer gets from drawing them. The gap
        number (in thousandths of text space) must shrink by exactly
        85 / 10 * 1000 = 8500 to make up for it."""
        team_name = "Example Swim Team"  # 17 characters
        original_gap = -2000
        pdf_bytes = make_packed_tj_pdf(team_name)
        src = write_temp_pdf(pdf_bytes, tmp_path)
        out = tmp_path / "out.pdf"

        format_report(str(src), str(out))

        reader = PdfReader(str(out))
        cs = ContentStream(reader.pages[0]["/Contents"], reader)
        tj_array = next(
            operands[0] for operands, operator in cs.operations if operator == b"TJ"
        )
        gap_value = next(
            float(item) for item in tj_array if isinstance(item, (int, float))
        )

        removed_width = len(team_name) * GLYPH_WIDTH / 1000.0 * 10  # font_size=10
        expected_gap = original_gap - removed_width / 10 * 1000.0
        assert gap_value == pytest.approx(expected_gap)


# ---------------------------------------------------------------------------
# Helper — build a minimal PDF whose header block uses a long chain of
# relative Td jumps (subtitle lines, session info, a table header row) that
# happens to drift back to x == LEFT_MARGIN_X well below the actual header,
# in a Session Report-style layout. Regression case: a coincidental margin
# match deep in the page body must not be mistaken for the header.
# ---------------------------------------------------------------------------

def make_drifting_td_pdf(team_name: str, table_header_word: str = "Round") -> bytes:
    """Team name at the real header position (Tm, near top), followed by a
    chain of Td jumps whose cumulative y drifts to a small negative number
    — still "near top" under an unbounded y <= HEADER_BAND check, but not
    actually near the top of the page once mapped through the flipped
    coordinate system's cm."""
    content = "\n".join([
        "1 0 0 -1 0 792 cm",
        "BT",
        "/F1 8.55 Tf",
        "1 0 0 -1 18 45.5 Tm",
        f"({team_name}) Tj",
        "0 -13.4 Td",
        "(Subtitle line) Tj",
        "0 -14.4 Td",
        "(Session info line) Tj",
        "0 -25.9 Td",
        f"({table_header_word}) Tj",
        "ET",
    ]).encode("latin-1")

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    from pypdf.generic import StreamObject
    content_obj = StreamObject()
    content_obj.set_data(content)
    page[NameObject("/Contents")] = writer._add_object(content_obj)

    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({
            NameObject("/F1"): writer._add_object(font),
        })
    })

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class TestDriftingTdCoincidence:
    def test_table_header_below_page_header_is_not_erased(self, tmp_path):
        """Regression test: a Session Report's table header ("Round") sits
        well below the actual page header, but a chain of Td jumps between
        them can drift the cursor back to x == LEFT_MARGIN_X with a small
        negative y — which used to satisfy _near_top's unbounded check and
        get mistaken for the team-name header."""
        pdf_bytes = make_drifting_td_pdf("Example Swim Team", "Round")
        src = write_temp_pdf(pdf_bytes, tmp_path)
        out = tmp_path / "out.pdf"

        format_report(str(src), str(out))

        text = PdfReader(str(out)).pages[0].extract_text()
        assert "Example" not in text
        assert "Round" in text


# ---------------------------------------------------------------------------
# Core behavior
# ---------------------------------------------------------------------------

class TestFormatReport:
    def test_erases_team_name_relative_td(self, tmp_path):
        pdf_bytes = make_meet_manager_pdf("Example Swim Team", num_pages=1,
                                           use_tm_for_team=False)
        src = write_temp_pdf(pdf_bytes, tmp_path)
        out = tmp_path / "out.pdf"

        format_report(str(src), str(out))

        reader = PdfReader(str(out))
        text = reader.pages[0].extract_text()
        assert "Example" not in text
        assert "Page 1" in text

    def test_erases_team_name_absolute_tm(self, tmp_path):
        pdf_bytes = make_meet_manager_pdf("Example Swim Team", num_pages=1,
                                           use_tm_for_team=True)
        src = write_temp_pdf(pdf_bytes, tmp_path)
        out = tmp_path / "out.pdf"

        format_report(str(src), str(out))

        reader = PdfReader(str(out))
        text = reader.pages[0].extract_text()
        assert "Example" not in text
        assert "Page 1" in text

    def test_erases_across_multiple_pages(self, tmp_path):
        pdf_bytes = make_meet_manager_pdf("Some Other Team", num_pages=5)
        src = write_temp_pdf(pdf_bytes, tmp_path)
        out = tmp_path / "out.pdf"

        format_report(str(src), str(out))

        reader = PdfReader(str(out))
        assert len(reader.pages) == 5
        for page in reader.pages:
            text = page.extract_text()
            assert "Some Other Team" not in text
            assert "Page 1" in text

    def test_works_regardless_of_team_name_content(self, tmp_path):
        """Detection is position-based, not a hardcoded string match."""
        pdf_bytes = make_meet_manager_pdf("Totally Different Aquatics Club")
        src = write_temp_pdf(pdf_bytes, tmp_path)
        out = tmp_path / "out.pdf"

        format_report(str(src), str(out))

        text = PdfReader(str(out)).pages[0].extract_text()
        assert "Totally Different Aquatics Club" not in text

    def test_body_text_below_header_is_untouched(self, tmp_path):
        pdf_bytes = make_meet_manager_pdf("Example Swim Team")
        src = write_temp_pdf(pdf_bytes, tmp_path)
        out = tmp_path / "out.pdf"

        format_report(str(src), str(out))

        text = PdfReader(str(out)).pages[0].extract_text()
        assert "Body text below" in text

    def test_default_output_path(self, tmp_path, monkeypatch):
        pdf_bytes = make_meet_manager_pdf("Example Swim Team")
        src = write_temp_pdf(pdf_bytes, tmp_path)
        default_out = tmp_path / "input_formatted.pdf"

        format_report(str(src), str(default_out))
        assert default_out.exists()


# ---------------------------------------------------------------------------
# Safety / input validation
# ---------------------------------------------------------------------------

class TestSafety:
    def test_rejects_non_pdf_extension(self, tmp_path):
        p = tmp_path / "input.txt"
        p.write_text("not a pdf")
        with pytest.raises(ValueError, match="must be a .pdf"):
            format_report(str(p), str(tmp_path / "out.pdf"))

    def test_rejects_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            format_report(str(tmp_path / "missing.pdf"), str(tmp_path / "out.pdf"))

    def test_rejects_oversized_input(self, tmp_path, monkeypatch):
        pdf_bytes = make_meet_manager_pdf("Example Swim Team")
        src = write_temp_pdf(pdf_bytes, tmp_path)
        monkeypatch.setattr("format_report.MAX_INPUT_BYTES", 10)
        with pytest.raises(ValueError, match="too large"):
            format_report(str(src), str(tmp_path / "out.pdf"))

    def test_rejects_directory_as_input(self, tmp_path):
        d = tmp_path / "dir.pdf"
        d.mkdir()
        with pytest.raises(FileNotFoundError):
            format_report(str(d), str(tmp_path / "out.pdf"))

    def test_writes_atomically_no_partial_file_on_failure(self, tmp_path, monkeypatch):
        pdf_bytes = make_meet_manager_pdf("Example Swim Team")
        src = write_temp_pdf(pdf_bytes, tmp_path)
        out = tmp_path / "out.pdf"

        def boom(self, f):
            raise RuntimeError("simulated write failure")

        monkeypatch.setattr(PdfWriter, "write", boom)
        with pytest.raises(RuntimeError):
            format_report(str(src), str(out))
        assert not out.exists()
        assert list(tmp_path.glob("*.tmp")) == []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class TestCLI:
    def test_replace_flag_exits_nonzero(self, tmp_path, capsys, monkeypatch):
        import sys
        import format_report as module

        pdf_bytes = make_meet_manager_pdf("Example Swim Team")
        src = write_temp_pdf(pdf_bytes, tmp_path)

        monkeypatch.setattr(sys, "argv", ["format_report.py", "--replace", "X", str(src)])
        with pytest.raises(SystemExit) as exc_info:
            module.main()
        assert exc_info.value.code == 1
        assert "not yet supported" in capsys.readouterr().out

    def test_no_args_prints_usage_and_exits_nonzero(self, capsys, monkeypatch):
        import sys
        import format_report as module

        monkeypatch.setattr(sys, "argv", ["format_report.py"])
        with pytest.raises(SystemExit) as exc_info:
            module.main()
        assert exc_info.value.code == 1

    def test_help_flag_exits_zero(self, capsys, monkeypatch):
        import sys
        import format_report as module

        monkeypatch.setattr(sys, "argv", ["format_report.py", "--help"])
        with pytest.raises(SystemExit) as exc_info:
            module.main()
        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# Regression tests — real Meet Manager output
#
# These heat sheets (in ../examples/, shared with heat-sheet-stamper) are
# publicly published meet programs, unlike the private team-fees/team-report
# examples in this tool's own examples/ (gitignored — see .gitignore). They
# exercise the tool against real Meet Manager content streams — including
# different export shapes for the same visual header, e.g. the team name
# and "Page N" text drawn as two separate operators vs. packed into one TJ
# array with a large kerning-style gap — rather than only synthetic PDFs.
# ---------------------------------------------------------------------------

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"

REAL_EXAMPLES = [
    ("ngsl-invitational-2022.pdf", 7, "Habersham Hurricanes"),
    ("osaa-state-championships-2026-finals.pdf", 9, "OSAA State Championship Meet"),
    ("osaa-state-championships-2024-prelims.pdf", 9, "OSAA State Championship Meet"),
]


class TestRealExamples:
    @pytest.mark.parametrize("filename,expected_pages,header_label", REAL_EXAMPLES)
    def test_erases_header_label_on_every_page(
        self, tmp_path, filename, expected_pages, header_label
    ):
        src = EXAMPLES_DIR / filename
        out = tmp_path / "out.pdf"

        format_report(str(src), str(out))

        reader = PdfReader(str(out))
        assert len(reader.pages) == expected_pages
        for page in reader.pages:
            text = page.extract_text()
            assert header_label not in text
            assert "Page " in text

            # Guards against partial erasure (e.g. only the label's first
            # character removed) slipping past the exact-string check above.
            # Scoped to the header line itself, since some of the label's
            # words legitimately reappear in body text below it (e.g. the
            # meet organizer line under the OSAA reports).
            header_line = next(l for l in text.splitlines() if "Page " in l)
            for word in header_label.split():
                assert word not in header_line

    @pytest.mark.parametrize("filename,expected_pages,header_label", REAL_EXAMPLES)
    def test_header_stays_right_justified(
        self, tmp_path, filename, expected_pages, header_label
    ):
        """
        Erasing the team name must not shift 'HY-TEK's MEET MANAGER...'
        out of its original right-justified position — regression test for
        a bug where blanking a packed TJ array's leading glyph run dropped
        its advance width from the pen math without compensating for it
        (see _blank_leading_run), pulling the rest of the header left.

        Rendered to pixels rather than checked via text extraction: pypdf's
        layout-mode column position is unreliable once the leading span is
        blank, so pixel position against the real rasterizer is the only
        ground truth that matches what actually prints/displays.
        """
        src = EXAMPLES_DIR / filename
        out = tmp_path / "out.pdf"

        format_report(str(src), str(out))

        # All real examples are Letter-width (612pt); "HY-TEK's MEET
        # MANAGER..." always starts past x=310 and team names always end
        # before it, so clipping there isolates it from both team-name text
        # and the decorative rule lines Meet Manager draws around x=299.
        def hy_tek_left_edge_px(pdf_path):
            page = pymupdf.open(str(pdf_path))[0]
            clip = pymupdf.Rect(310, 30, page.rect.width, 50)
            pix = page.get_pixmap(clip=clip, dpi=200)
            for x in range(pix.width):
                for y in range(pix.height):
                    if sum(pix.pixel(x, y)) < 600:  # non-white pixel
                        return x
            return None

        original_x = hy_tek_left_edge_px(src)
        formatted_x = hy_tek_left_edge_px(out)
        assert original_x is not None and formatted_x is not None
        assert abs(formatted_x - original_x) <= 2

    @pytest.mark.parametrize("filename,expected_pages,header_label", REAL_EXAMPLES)
    def test_body_text_preserved(self, tmp_path, filename, expected_pages, header_label):
        src = EXAMPLES_DIR / filename
        out = tmp_path / "out.pdf"

        format_report(str(src), str(out))

        original_text = PdfReader(str(src)).pages[0].extract_text()
        stamped_text = PdfReader(str(out)).pages[0].extract_text()
        # Every line except the erased header label survives untouched.
        for line in original_text.splitlines():
            if header_label in line:
                continue
            assert line in stamped_text
