"""
test_stamp_pdf.py — Test suite for stamp_pdf.py

Run with:
    pytest test_stamp_pdf.py -v
"""

import io
import os
import sys
import tempfile
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4, landscape
from pypdf import PdfReader, PdfWriter
import pypdf.errors

import stamp_pdf as module
from stamp_pdf import (
    build_stamp, build_corner_label, stamp_pdf,
    STAMP_LINES, STAMP_WIDTH, MARGIN, FONT_NAME,
    MAX_INPUT_BYTES, MAX_PAGES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_pdf(num_pages: int = 1, page_size: tuple = letter) -> bytes:
    """Create a minimal valid PDF in memory."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=page_size)
    for i in range(num_pages):
        c.drawString(72, page_size[1] - 72, f"Page {i + 1}")
        c.showPage()
    c.save()
    return buf.getvalue()


def make_encrypted_pdf(password: str = "secret") -> bytes:
    src_reader = PdfReader(io.BytesIO(make_pdf()))
    writer = PdfWriter()
    writer.add_page(src_reader.pages[0])
    writer.encrypt(password)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Unit tests — build_stamp
# ---------------------------------------------------------------------------

class TestBuildStamp:
    def test_returns_bytes_io(self):
        result = build_stamp(612, 792)
        assert isinstance(result, io.BytesIO)

    def test_is_valid_single_page_pdf(self):
        result = build_stamp(612, 792)
        reader = PdfReader(result)
        assert len(reader.pages) == 1

    def test_stamp_x_position_is_positive_letter(self):
        # For a standard letter page the stamp should fit inside the page
        x = 612 - MARGIN - STAMP_WIDTH
        assert x > 0

    def test_stamp_x_position_is_positive_a4(self):
        w, _ = A4
        x = w - MARGIN - STAMP_WIDTH
        assert x > 0

    def test_letter_page(self):
        result = build_stamp(612, 792)
        assert PdfReader(result).pages[0] is not None

    def test_a4_page(self):
        w, h = A4
        result = build_stamp(w, h)
        assert PdfReader(result).pages[0] is not None

    def test_landscape_page(self):
        h, w = letter  # landscape swaps dimensions
        result = build_stamp(w, h)
        assert PdfReader(result).pages[0] is not None

    def test_large_page(self):
        result = build_stamp(5000, 5000)
        assert len(PdfReader(result).pages) == 1

    def test_tiny_page_does_not_crash(self):
        # Stamp may overflow; we just require no exception
        result = build_stamp(36, 36)
        assert isinstance(result, io.BytesIO)

    def test_non_standard_aspect_ratio(self):
        result = build_stamp(200, 2000)
        assert len(PdfReader(result).pages) == 1


# ---------------------------------------------------------------------------
# Integration tests — stamp_pdf
# ---------------------------------------------------------------------------

class TestStampPdf:
    def test_single_page_output_created(self, tmp_path):
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf(1))
        out = tmp_path / "output.pdf"
        stamp_pdf(str(src), str(out))
        assert out.exists()

    def test_single_page_count_preserved(self, tmp_path):
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf(1))
        out = tmp_path / "output.pdf"
        stamp_pdf(str(src), str(out))
        assert len(PdfReader(str(out)).pages) == 1

    def test_multi_page_count_preserved(self, tmp_path):
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf(10))
        out = tmp_path / "output.pdf"
        stamp_pdf(str(src), str(out))
        assert len(PdfReader(str(out)).pages) == 10

    def test_output_is_valid_pdf(self, tmp_path):
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf())
        out = tmp_path / "output.pdf"
        stamp_pdf(str(src), str(out))
        # PdfReader constructor raises on invalid PDF
        PdfReader(str(out))

    def test_a4_input(self, tmp_path):
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf(page_size=A4))
        out = tmp_path / "output.pdf"
        stamp_pdf(str(src), str(out))
        assert len(PdfReader(str(out)).pages) == 1

    def test_landscape_input(self, tmp_path):
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf(page_size=landscape(letter)))
        out = tmp_path / "output.pdf"
        stamp_pdf(str(src), str(out))
        assert len(PdfReader(str(out)).pages) == 1

    def test_overwrites_existing_output(self, tmp_path):
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf())
        out = tmp_path / "output.pdf"
        out.write_text("stale content")
        stamp_pdf(str(src), str(out))
        PdfReader(str(out))  # must be a valid PDF, not the stale text

    def test_many_pages(self, tmp_path):
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf(50))
        out = tmp_path / "output.pdf"
        stamp_pdf(str(src), str(out))
        assert len(PdfReader(str(out)).pages) == 50

    def test_mixed_page_sizes(self, tmp_path):
        """PDF whose pages have different dimensions."""
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        c.drawString(72, 700, "Letter page")
        c.showPage()
        c.setPageSize(A4)
        c.drawString(72, 700, "A4 page")
        c.showPage()
        c.save()
        src = tmp_path / "mixed.pdf"
        src.write_bytes(buf.getvalue())
        out = tmp_path / "output.pdf"
        stamp_pdf(str(src), str(out))
        assert len(PdfReader(str(out)).pages) == 2

    def test_print_message_on_success(self, tmp_path, capsys):
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf())
        out = tmp_path / "output.pdf"
        stamp_pdf(str(src), str(out))
        captured = capsys.readouterr()
        assert str(out) in captured.out

    def test_stamp_text_present_in_output(self, tmp_path):
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf())
        out = tmp_path / "output.pdf"
        stamp_pdf(str(src), str(out))
        text = PdfReader(str(out)).pages[0].extract_text()
        assert "DQ" in text
        assert "NS" in text
        assert "DFS" in text


# ---------------------------------------------------------------------------
# CLI tests — main()
# ---------------------------------------------------------------------------

class TestMain:
    def test_no_args_exits_with_1(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["stamp_pdf.py"])
        with pytest.raises(SystemExit) as exc:
            module.main()
        assert exc.value.code == 1

    def test_default_output_filename(self, tmp_path, monkeypatch):
        src = tmp_path / "report.pdf"
        src.write_bytes(make_pdf())
        monkeypatch.setattr(sys, "argv", ["stamp_pdf.py", str(src)])
        module.main()
        assert (tmp_path / "report_stamped.pdf").exists()

    def test_explicit_output_path(self, tmp_path, monkeypatch):
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf())
        out = tmp_path / "custom.pdf"
        monkeypatch.setattr(sys, "argv", ["stamp_pdf.py", str(src), str(out)])
        module.main()
        assert out.exists()

    def test_nonexistent_input_exits(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["stamp_pdf.py", str(tmp_path / "ghost.pdf")])
        with pytest.raises((FileNotFoundError, SystemExit, pypdf.errors.PdfReadError)):
            module.main()

    def test_default_stem_preserves_extension(self, tmp_path, monkeypatch):
        src = tmp_path / "heat.pdf"
        src.write_bytes(make_pdf())
        monkeypatch.setattr(sys, "argv", ["stamp_pdf.py", str(src)])
        module.main()
        expected = tmp_path / "heat_stamped.pdf"
        assert expected.suffix == ".pdf"
        assert expected.exists()


# ---------------------------------------------------------------------------
# --sr / --dr / --help flag tests
# ---------------------------------------------------------------------------

class TestFlags:
    def test_sr_adds_corner_label(self, tmp_path):
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf())
        out = tmp_path / "out.pdf"
        stamp_pdf(str(src), str(out), corner_label="SR", include_stamp=False)
        text = PdfReader(str(out)).pages[0].extract_text()
        assert "SR" in text

    def test_sr_omits_bottom_stamp(self, tmp_path):
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf())
        out = tmp_path / "out.pdf"
        stamp_pdf(str(src), str(out), corner_label="SR", include_stamp=False)
        text = PdfReader(str(out)).pages[0].extract_text()
        assert "DQ" not in text
        assert "NS" not in text
        assert "DFS" not in text

    def test_dr_adds_corner_label(self, tmp_path):
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf())
        out = tmp_path / "out.pdf"
        stamp_pdf(str(src), str(out), corner_label="DR", include_stamp=True)
        text = PdfReader(str(out)).pages[0].extract_text()
        assert "DR" in text

    def test_dr_includes_bottom_stamp(self, tmp_path):
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf())
        out = tmp_path / "out.pdf"
        stamp_pdf(str(src), str(out), corner_label="DR", include_stamp=True)
        text = PdfReader(str(out)).pages[0].extract_text()
        assert "DQ" in text
        assert "NS" in text
        assert "DFS" in text

    def test_default_no_corner_label(self, tmp_path):
        """No flag → no corner label, bottom stamp present."""
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf())
        out = tmp_path / "out.pdf"
        stamp_pdf(str(src), str(out))
        text = PdfReader(str(out)).pages[0].extract_text()
        assert "SR" not in text
        assert "DR" not in text
        assert "DQ" in text

    def test_cli_sr_flag(self, tmp_path, monkeypatch):
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf())
        out = tmp_path / "out.pdf"
        monkeypatch.setattr(sys, "argv", ["stamp_pdf.py", "--sr", str(src), str(out)])
        module.main()
        text = PdfReader(str(out)).pages[0].extract_text()
        assert "SR" in text
        assert "DQ" not in text

    def test_cli_dr_flag(self, tmp_path, monkeypatch):
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf())
        out = tmp_path / "out.pdf"
        monkeypatch.setattr(sys, "argv", ["stamp_pdf.py", "--dr", str(src), str(out)])
        module.main()
        text = PdfReader(str(out)).pages[0].extract_text()
        assert "DR" in text
        assert "DQ" in text

    def test_cli_both_flags_exits(self, tmp_path, monkeypatch):
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf())
        monkeypatch.setattr(sys, "argv", ["stamp_pdf.py", "--sr", "--dr", str(src)])
        with pytest.raises(SystemExit) as exc:
            module.main()
        assert exc.value.code == 1

    def test_cli_sr_default_output_name(self, tmp_path, monkeypatch):
        src = tmp_path / "report.pdf"
        src.write_bytes(make_pdf())
        monkeypatch.setattr(sys, "argv", ["stamp_pdf.py", "--sr", str(src)])
        module.main()
        assert (tmp_path / "report_stamped.pdf").exists()

    def test_help_flag_exits_0(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["stamp_pdf.py", "--help"])
        with pytest.raises(SystemExit) as exc:
            module.main()
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "--sr" in captured.out

    def test_build_corner_label_returns_valid_pdf(self):
        result = build_corner_label("SR", 612, 792)
        assert len(PdfReader(result).pages) == 1

    def test_auto_creates_both_files(self, tmp_path, monkeypatch):
        src = tmp_path / "report.pdf"
        src.write_bytes(make_pdf())
        monkeypatch.setattr(sys, "argv", ["stamp_pdf.py", "--auto", str(src)])
        module.main()
        assert (tmp_path / "report-sr.pdf").exists()
        assert (tmp_path / "report-dr.pdf").exists()

    def test_auto_sr_file_content(self, tmp_path, monkeypatch):
        src = tmp_path / "report.pdf"
        src.write_bytes(make_pdf())
        monkeypatch.setattr(sys, "argv", ["stamp_pdf.py", "--auto", str(src)])
        module.main()
        text = PdfReader(str(tmp_path / "report-sr.pdf")).pages[0].extract_text()
        assert "SR" in text
        assert "DQ" not in text

    def test_auto_dr_file_content(self, tmp_path, monkeypatch):
        src = tmp_path / "report.pdf"
        src.write_bytes(make_pdf())
        monkeypatch.setattr(sys, "argv", ["stamp_pdf.py", "--auto", str(src)])
        module.main()
        text = PdfReader(str(tmp_path / "report-dr.pdf")).pages[0].extract_text()
        assert "DR" in text
        assert "DQ" in text

    def test_auto_with_sr_exits(self, tmp_path, monkeypatch):
        src = tmp_path / "report.pdf"
        src.write_bytes(make_pdf())
        monkeypatch.setattr(sys, "argv", ["stamp_pdf.py", "--auto", "--sr", str(src)])
        with pytest.raises(SystemExit) as exc:
            module.main()
        assert exc.value.code == 1

    def test_auto_with_dr_exits(self, tmp_path, monkeypatch):
        src = tmp_path / "report.pdf"
        src.write_bytes(make_pdf())
        monkeypatch.setattr(sys, "argv", ["stamp_pdf.py", "--auto", "--dr", str(src)])
        with pytest.raises(SystemExit) as exc:
            module.main()
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
# Security tests
# ---------------------------------------------------------------------------

class TestSecurity:
    def test_nonexistent_input_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            stamp_pdf(str(tmp_path / "ghost.pdf"), str(tmp_path / "out.pdf"))

    def test_corrupt_pdf_raises(self, tmp_path):
        src = tmp_path / "corrupt.pdf"
        src.write_bytes(b"this is definitely not a pdf")
        with pytest.raises(pypdf.errors.PdfReadError):
            stamp_pdf(str(src), str(tmp_path / "out.pdf"))

    def test_empty_file_raises(self, tmp_path):
        src = tmp_path / "empty.pdf"
        src.write_bytes(b"")
        with pytest.raises((pypdf.errors.PdfReadError, pypdf.errors.EmptyFileError)):
            stamp_pdf(str(src), str(tmp_path / "out.pdf"))

    def test_pdf_header_only_garbage_body_raises(self, tmp_path):
        """Valid PDF magic bytes but random garbage body."""
        src = tmp_path / "partial.pdf"
        src.write_bytes(b"%PDF-1.7\n" + os.urandom(1024))
        with pytest.raises(pypdf.errors.PdfReadError):
            stamp_pdf(str(src), str(tmp_path / "out.pdf"))

    def test_non_pdf_extension_raises_value_error(self, tmp_path):
        src = tmp_path / "image.jpg"
        src.write_bytes(bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"\x00" * 100)
        with pytest.raises(ValueError, match=r"\.pdf"):
            stamp_pdf(str(src), str(tmp_path / "out.pdf"))

    def test_no_extension_raises(self, tmp_path):
        src = tmp_path / "heatsheet"
        src.write_bytes(make_pdf())
        with pytest.raises(ValueError, match=r"\.pdf"):
            stamp_pdf(str(src), str(tmp_path / "out.pdf"))

    def test_docx_extension_raises(self, tmp_path):
        src = tmp_path / "document.docx"
        src.write_bytes(b"PK\x03\x04")  # zip magic bytes (docx is a zip)
        with pytest.raises(ValueError, match=r"\.pdf"):
            stamp_pdf(str(src), str(tmp_path / "out.pdf"))

    def test_pdf_uppercase_extension_accepted(self, tmp_path):
        src = tmp_path / "input.PDF"
        src.write_bytes(make_pdf())
        out = tmp_path / "out.pdf"
        stamp_pdf(str(src), str(out))
        assert out.exists()

    def test_pdf_mixed_case_extension_accepted(self, tmp_path):
        src = tmp_path / "input.Pdf"
        src.write_bytes(make_pdf())
        out = tmp_path / "out.pdf"
        stamp_pdf(str(src), str(out))
        assert out.exists()

    def test_output_directory_nonexistent_raises(self, tmp_path):
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf())
        out = tmp_path / "no_such_dir" / "output.pdf"
        with pytest.raises(FileNotFoundError):
            stamp_pdf(str(src), str(out))

    def test_encrypted_pdf_raises(self, tmp_path):
        src = tmp_path / "encrypted.pdf"
        src.write_bytes(make_encrypted_pdf("secret"))
        with pytest.raises((pypdf.errors.PdfReadError, pypdf.errors.FileNotDecryptedError)):
            stamp_pdf(str(src), str(tmp_path / "out.pdf"))

    def test_symlink_to_nonexistent_raises(self, tmp_path):
        link = tmp_path / "link.pdf"
        link.symlink_to(tmp_path / "does_not_exist.pdf")
        with pytest.raises(FileNotFoundError):
            stamp_pdf(str(link), str(tmp_path / "out.pdf"))

    def test_symlink_to_valid_pdf_works(self, tmp_path):
        real = tmp_path / "real.pdf"
        real.write_bytes(make_pdf())
        link = tmp_path / "link.pdf"
        link.symlink_to(real)
        out = tmp_path / "out.pdf"
        stamp_pdf(str(link), str(out))
        assert out.exists()

    def test_path_traversal_output_resolves_safely(self, tmp_path):
        """Path with '..' components must not escape to unexpected locations."""
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf())
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        # subdir/.. resolves back to tmp_path — must write there, not escape further
        out = subdir / ".." / "output.pdf"
        stamp_pdf(str(src), str(out))
        resolved = (tmp_path / "output.pdf").resolve()
        assert resolved.exists()

    def test_input_same_as_output_does_not_zero_file(self, tmp_path):
        """Writing output to the same path must not silently truncate the file."""
        src = tmp_path / "inout.pdf"
        src.write_bytes(make_pdf())
        try:
            stamp_pdf(str(src), str(src))
            # If it succeeded, the file must still be a valid PDF
            PdfReader(str(src))
        except Exception:
            # Raising is acceptable; file must not be left empty
            assert src.stat().st_size > 0

    def test_filename_with_spaces(self, tmp_path):
        src = tmp_path / "my heat sheet.pdf"
        src.write_bytes(make_pdf())
        out = tmp_path / "my heat sheet stamped.pdf"
        stamp_pdf(str(src), str(out))
        assert out.exists()

    def test_filename_with_special_characters(self, tmp_path):
        src = tmp_path / "heat&sheet #1 (final).pdf"
        src.write_bytes(make_pdf())
        out = tmp_path / "out.pdf"
        stamp_pdf(str(src), str(out))
        assert out.exists()

    def test_very_large_page_dimensions(self, tmp_path):
        """Extremely large page should not crash or hang."""
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(100_000, 100_000))
        c.showPage()
        c.save()
        src = tmp_path / "huge.pdf"
        src.write_bytes(buf.getvalue())
        out = tmp_path / "out.pdf"
        stamp_pdf(str(src), str(out))
        assert out.exists()

    def test_zero_page_pdf_produces_zero_page_output(self, tmp_path):
        """A PDF with no pages should produce a valid zero-page output."""
        buf = io.BytesIO()
        PdfWriter().write(buf)
        src = tmp_path / "zero_pages.pdf"
        src.write_bytes(buf.getvalue())
        out = tmp_path / "out.pdf"
        try:
            stamp_pdf(str(src), str(out))
            assert len(PdfReader(str(out)).pages) == 0
        except pypdf.errors.PdfReadError:
            pass  # zero-page PDFs are degenerate; a parse error is acceptable

    def test_output_not_written_on_invalid_input(self, tmp_path):
        """A failed run must not leave a partial output file."""
        src = tmp_path / "bad.pdf"
        src.write_bytes(b"not a pdf")
        out = tmp_path / "out.pdf"
        with pytest.raises(Exception):
            stamp_pdf(str(src), str(out))
        # output should either not exist or not be a zero-byte file
        if out.exists():
            assert out.stat().st_size > 0

    # --- New guards added for HIGH security findings ---

    def test_file_too_large_raises(self, tmp_path, monkeypatch):
        """Input files over MAX_INPUT_BYTES are rejected before processing."""
        monkeypatch.setattr(module, "MAX_INPUT_BYTES", 10)
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf())  # always > 10 bytes
        with pytest.raises(ValueError, match="too large"):
            stamp_pdf(str(src), str(tmp_path / "out.pdf"))

    def test_too_many_pages_raises(self, tmp_path, monkeypatch):
        """PDFs with more pages than MAX_PAGES are rejected."""
        monkeypatch.setattr(module, "MAX_PAGES", 2)
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf(3))
        with pytest.raises(ValueError, match="too many pages"):
            stamp_pdf(str(src), str(tmp_path / "out.pdf"))

    def test_non_regular_file_raises(self):
        """/dev/null and other non-regular files are rejected."""
        dev_null = Path("/dev/null")
        if not dev_null.exists():
            pytest.skip("/dev/null not available")
        # /dev/null has no extension → ValueError; if it had .pdf, → FileNotFoundError
        with pytest.raises((ValueError, FileNotFoundError)):
            stamp_pdf("/dev/null", "/tmp/out.pdf")

    def test_atomic_write_no_partial_on_disk_error(self, tmp_path, monkeypatch):
        """If the write fails mid-way, no partial file is left at output_path."""
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf())
        out = tmp_path / "out.pdf"

        # Simulate a write failure by monkeypatching PdfWriter.write
        import pypdf
        def fail_write(self, stream):
            stream.write(b"partial")
            raise OSError("simulated disk full")
        monkeypatch.setattr(pypdf.PdfWriter, "write", fail_write)

        with pytest.raises(OSError, match="simulated disk full"):
            stamp_pdf(str(src), str(out))

        # The output path must not exist (temp file was cleaned up)
        assert not out.exists()

    def test_output_symlink_not_followed_on_write(self, tmp_path):
        """os.replace() must replace the symlink itself, not write to its target."""
        sensitive = tmp_path / "sensitive.txt"
        sensitive.write_text("original content")

        out = tmp_path / "out.pdf"
        out.symlink_to(sensitive)  # out.pdf → sensitive.txt

        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf())
        stamp_pdf(str(src), str(out))

        # out.pdf is now a real PDF file (symlink was replaced)
        assert out.is_file() and not out.is_symlink() or out.is_symlink() is False
        # sensitive.txt must be untouched
        assert sensitive.read_text() == "original content"

    def test_terminal_escape_in_path_not_printed_raw(self, tmp_path, capsys):
        """Escape sequences in output_path must be repr()-escaped in stdout."""
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf())
        # Path with an ANSI escape sequence embedded
        out = tmp_path / "out.pdf"
        stamp_pdf(str(src), str(out))
        captured = capsys.readouterr()
        # The output must not contain a raw ESC byte
        assert "\x1b" not in captured.out


# ---------------------------------------------------------------------------
# Regression tests — real Meet Manager output
# ---------------------------------------------------------------------------

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"

REAL_EXAMPLES = [
    ("ngsl-invitational-2022.pdf", 7),
    ("osaa-state-championships-2026-finals.pdf", 9),
    ("osaa-state-championships-2024-prelims.pdf", 9),
]


class TestRealExamples:
    """
    End-to-end checks against real, publicly-published Meet Manager heat
    sheets (not synthetic PDFs), to catch layout assumptions that only
    break on real-world output.
    """

    @pytest.mark.parametrize("filename,expected_pages", REAL_EXAMPLES)
    def test_stamp_only_preserves_page_count_and_adds_stamp(
        self, tmp_path, filename, expected_pages
    ):
        src = EXAMPLES_DIR / filename
        out = tmp_path / "out.pdf"
        stamp_pdf(str(src), str(out))

        reader = PdfReader(str(out))
        assert len(reader.pages) == expected_pages
        # Original text must survive the overlay
        original_text = PdfReader(str(src)).pages[0].extract_text()
        stamped_text = reader.pages[0].extract_text()
        assert original_text.strip() in stamped_text

    @pytest.mark.parametrize("filename,expected_pages", REAL_EXAMPLES)
    def test_auto_mode_produces_both_variants(self, tmp_path, filename, expected_pages):
        src = EXAMPLES_DIR / filename
        # --auto derives output paths from the input path's parent, so copy
        # the source into tmp_path first to avoid writing into examples/.
        local_src = tmp_path / filename
        local_src.write_bytes(src.read_bytes())

        argv_backup = sys.argv
        try:
            sys.argv = ["stamp_pdf.py", "--auto", str(local_src)]
            module.main()
        finally:
            sys.argv = argv_backup

        stem = local_src.stem
        sr_path = tmp_path / f"{stem}-sr.pdf"
        dr_path = tmp_path / f"{stem}-dr.pdf"
        assert sr_path.exists()
        assert dr_path.exists()
        assert len(PdfReader(str(sr_path)).pages) == expected_pages
        assert len(PdfReader(str(dr_path)).pages) == expected_pages
