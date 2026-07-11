# meet-report-formatter

Erases the host-team label that HY-TEK Meet Manager prints on every page of
its report PDFs (Team Entries, Team Fees, etc.) — e.g. "Chehalem Swim Team"
in the top-left corner of every page.

## Requirements

- Python 3.9+
- [pypdf](https://pypdf.readthedocs.io/) `>=6,<7`

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Activate the venv at the start of each session with `source .venv/bin/activate`.

## Usage

```
python3 format_report.py input.pdf [output.pdf]
```

If `output.pdf` is omitted the result is saved as `input_formatted.pdf` in
the same directory.

## How it works

Meet Manager always draws the host team's name as the leftmost text on the
header line of every page — right after "HY-TEK's MEET MANAGER ... Page N".
This tool walks each page's PDF content stream, finds the text-drawing
operator whose position lands at the page's left margin on that header line,
and blanks it. Detection is positional, not string-matching, so it works
regardless of which team hosted the meet.

Different Meet Manager exports encode that header line differently:

- **Two separate operators** — the team name and the "Page N" text are each
  their own `Tj`/`TJ` call with their own position. The whole team-name
  operator gets blanked.
- **One packed operator** — some exports draw the entire header line
  (team name + "Page N" text) as a single `TJ` array, using an oversized
  horizontal-jump number (in the thousands) where normal kerning stays under
  ~150, to create the visual gap between the two. The tool splits the array
  at that gap and blanks only the leading (team-name) portion, leaving the
  "Page N" text after the gap untouched.

The header line is also located in either a flipped (`Tm`/`cm` with a −1
y-scale) or standard PDF coordinate system — both appear in real Meet
Manager output — so "near the top of the page" is checked in both
directions rather than assuming one.

## Replacing the label (not yet supported)

The original ask includes eventually replacing the label with a
caller-supplied name, not just erasing it. That turned out to be unsafe with
the current approach: Meet Manager embeds **subsetted** fonts that only
contain the glyphs actually used elsewhere on the page. "Chehalem Swim Team"
has no embedded 'r' or 'k' glyph, for example — writing a replacement name
like "CST Sharks" into the same content stream renders missing/broken
glyphs.

`--replace` is stubbed to fail loudly rather than silently corrupt output.
The likely fix is to erase the original text (already safe) and overlay the
replacement as a new text box in a standard PDF font, the way
[heat-sheet-stamper](../heat-sheet-stamper/) draws its corner stamps —
rather than editing Meet Manager's original content stream in place.

## Development

Install dev dependencies (includes pytest and pylint):

```bash
pip install -r requirements-dev.txt
```

Run tests:

```bash
pytest test_format_report.py -v
```

Run linter:

```bash
pylint format_report.py
```

## Examples

Publicly-published Meet Manager reports live in [../examples/](../examples/)
at the repo root, shared with [heat-sheet-stamper](../heat-sheet-stamper/).
`TestRealExamples` in the test suite runs the tool end-to-end against every
file there.

This tool's own `examples/*.pdf` is gitignored by default, since real Meet
Manager report PDFs usually contain swimmers' names, ages, and times — drop
your own private samples there for manual testing:

```
python3 format_report.py examples/your-sample.pdf examples/your-sample_formatted.pdf
```
