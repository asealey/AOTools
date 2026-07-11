# AOTools

Swim meet officiating tools — heat sheet stamping, Daktronics timing log parsing, and Meet Manager report editing.

## Tools

| Tool | Purpose |
|---|---|
| [heat-sheet-stamper/](heat-sheet-stamper/) | Adds DQ/NS/DFS scoring stamps to swim meet heat sheet PDFs |
| [dak-malfunction-parser/](dak-malfunction-parser/) | Parses Daktronics Omnisport 2000 timing logs for malfunction analysis |
| [meet-report-formatter/](meet-report-formatter/) | Edits team labeling text on Meet Manager report PDFs |

Each tool is self-contained with its own README, dependencies, and tests. See the tool's own directory for usage.

Python tools use [uv](https://docs.astral.sh/uv/) for dependency management (`uv sync`, `uv run`) rather than `venv`/`pip`. New Python tools should follow the same pattern.

[examples/](examples/) holds real, publicly-published Meet Manager PDFs shared across tools for manual testing and regression tests. Each tool also has its own local `examples/` for tool-private samples that aren't safe to publish.
