# heatSheetStamper

Adds a DQ / NS / DFS scoring stamp to the bottom-right corner of every page in a swim meet heat sheet PDF.

## Requirements

- Python 3.9+
- [pypdf](https://pypdf.readthedocs.io/) `>=6,<7`
- [reportlab](https://www.reportlab.com/opensource/) `>=4`

Install dependencies:

```
pip install "pypdf>=6,<7" "reportlab>=4"
```

## Usage

```
python3 stamp_pdf.py input.pdf [output.pdf]
```

If `output.pdf` is omitted the stamped file is saved as `input_stamped.pdf` in the same directory.

**Example:**

```
python3 stamp_pdf.py examples/exampleHeatSheet.pdf
# → examples/exampleHeatSheet_stamped.pdf
```

## Stamp appearance

Three lines are added in hot pink (Helvetica-Bold), right-aligned in the bottom-right corner:

```
DQ __________
NS __________
DFS __________
```

The block is 1.5 inches wide with an 18 pt margin from the page edges. Font size is scaled automatically so the widest line fills exactly 1.5 inches regardless of the page size.

## Running tests

```
pip install pytest
pytest test_stamp_pdf.py -v
```

40 tests cover unit behavior, integration across page sizes, CLI argument handling, and security cases (corrupt files, encrypted PDFs, symlinks, path traversal, special filenames, and more).
