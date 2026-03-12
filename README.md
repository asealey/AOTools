# heatSheetStamper

Adds a DQ / NS / DFS scoring stamp to the bottom-right corner of every page in a swim meet heat sheet PDF.

## Requirements

- Python 3.9+
- [pypdf](https://pypdf.readthedocs.io/) `>=6,<7`
- [reportlab](https://www.reportlab.com/opensource/) `>=4`

Install dependencies:

```
pip install -r requirements.txt
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

## Safety limits

The tool enforces the following limits to guard against malicious or malformed input:

| Limit | Default | Constant |
|---|---|---|
| Maximum input file size | 100 MB | `MAX_INPUT_BYTES` |
| Maximum page count | 5,000 pages | `MAX_PAGES` |

Input must be a regular file (device files and named pipes are rejected). Page dimensions are validated for finite, positive values. Output is written atomically via a temp file so no partial output is left on failure.

## Running tests

```
pip install pytest
pytest test_stamp_pdf.py -v
```

48 tests cover unit behavior, integration across page sizes, CLI argument handling, and security cases including: corrupt/empty/encrypted PDFs, symlink attacks, path traversal, non-regular file input, decompression bomb limits, page count limits, atomic write safety, and terminal escape injection.
