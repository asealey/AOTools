"""
test_format_report.py — Test suite for format_report.py

Run with:
    pytest test_format_report.py -v
"""

import io
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject

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


def make_meet_manager_pdf(team_name: str = "Chehalem Swim Team",
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
# Core behavior
# ---------------------------------------------------------------------------

class TestFormatReport:
    def test_erases_team_name_relative_td(self, tmp_path):
        pdf_bytes = make_meet_manager_pdf("Chehalem Swim Team", num_pages=1,
                                           use_tm_for_team=False)
        src = write_temp_pdf(pdf_bytes, tmp_path)
        out = tmp_path / "out.pdf"

        format_report(str(src), str(out))

        reader = PdfReader(str(out))
        text = reader.pages[0].extract_text()
        assert "Chehalem" not in text
        assert "Page 1" in text

    def test_erases_team_name_absolute_tm(self, tmp_path):
        pdf_bytes = make_meet_manager_pdf("Chehalem Swim Team", num_pages=1,
                                           use_tm_for_team=True)
        src = write_temp_pdf(pdf_bytes, tmp_path)
        out = tmp_path / "out.pdf"

        format_report(str(src), str(out))

        reader = PdfReader(str(out))
        text = reader.pages[0].extract_text()
        assert "Chehalem" not in text
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
        pdf_bytes = make_meet_manager_pdf("Chehalem Swim Team")
        src = write_temp_pdf(pdf_bytes, tmp_path)
        out = tmp_path / "out.pdf"

        format_report(str(src), str(out))

        text = PdfReader(str(out)).pages[0].extract_text()
        assert "Body text below" in text

    def test_default_output_path(self, tmp_path, monkeypatch):
        pdf_bytes = make_meet_manager_pdf("Chehalem Swim Team")
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
        pdf_bytes = make_meet_manager_pdf("Chehalem Swim Team")
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
        pdf_bytes = make_meet_manager_pdf("Chehalem Swim Team")
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

        pdf_bytes = make_meet_manager_pdf("Chehalem Swim Team")
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
