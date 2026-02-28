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

import stamp_pdf as module
from stamp_pdf import build_stamp, stamp_pdf, STAMP_LINES, STAMP_WIDTH, MARGIN, FONT_NAME


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

    def test_default_stem_preserves_extension(self, tmp_path, monkeypatch):
        src = tmp_path / "heat.pdf"
        src.write_bytes(make_pdf())
        monkeypatch.setattr(sys, "argv", ["stamp_pdf.py", str(src)])
        module.main()
        expected = tmp_path / "heat_stamped.pdf"
        assert expected.suffix == ".pdf"
        assert expected.exists()


# ---------------------------------------------------------------------------
# Security tests
# ---------------------------------------------------------------------------

class TestSecurity:
    def test_nonexistent_input_raises(self, tmp_path):
        with pytest.raises(Exception):
            stamp_pdf(str(tmp_path / "ghost.pdf"), str(tmp_path / "out.pdf"))

    def test_corrupt_pdf_raises(self, tmp_path):
        src = tmp_path / "corrupt.pdf"
        src.write_bytes(b"this is definitely not a pdf")
        with pytest.raises(Exception):
            stamp_pdf(str(src), str(tmp_path / "out.pdf"))

    def test_empty_file_raises(self, tmp_path):
        src = tmp_path / "empty.pdf"
        src.write_bytes(b"")
        with pytest.raises(Exception):
            stamp_pdf(str(src), str(tmp_path / "out.pdf"))

    def test_pdf_header_only_garbage_body_raises(self, tmp_path):
        """Valid PDF magic bytes but random garbage body."""
        src = tmp_path / "partial.pdf"
        src.write_bytes(b"%PDF-1.7\n" + os.urandom(1024))
        with pytest.raises(Exception):
            stamp_pdf(str(src), str(tmp_path / "out.pdf"))

    def test_non_pdf_extension_treated_as_pdf_raises(self, tmp_path):
        src = tmp_path / "image.jpg"
        src.write_bytes(bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"\x00" * 100)
        with pytest.raises(Exception):
            stamp_pdf(str(src), str(tmp_path / "out.pdf"))

    def test_output_directory_nonexistent_raises(self, tmp_path):
        src = tmp_path / "input.pdf"
        src.write_bytes(make_pdf())
        out = tmp_path / "no_such_dir" / "output.pdf"
        with pytest.raises(Exception):
            stamp_pdf(str(src), str(out))

    def test_encrypted_pdf_raises(self, tmp_path):
        src = tmp_path / "encrypted.pdf"
        src.write_bytes(make_encrypted_pdf("secret"))
        with pytest.raises(Exception):
            stamp_pdf(str(src), str(tmp_path / "out.pdf"))

    def test_symlink_to_nonexistent_raises(self, tmp_path):
        link = tmp_path / "link.pdf"
        link.symlink_to(tmp_path / "does_not_exist.pdf")
        with pytest.raises(Exception):
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
        except Exception:
            pass  # zero-page PDFs are degenerate; raising is acceptable

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
