# CLAUDE.md — AOTools

Coding project. Implementation detail (parsing logic, PDF-editing internals,
bugs, test coverage) lives here — in code, commit history, and each tool's
own README — not in the SealVault Obsidian vault. The vault only holds a
one-line pointer back to this repo.

## What this is

Monorepo of independent swim-meet-officiating tools:

| Tool | Purpose |
|---|---|
| `heat-sheet-stamper/` | Adds DQ/NS/DFS scoring stamps to heat sheet PDFs |
| `dak-malfunction-parser/` | Parses Daktronics Omnisport 2000 timing logs |
| `meet-report-formatter/` | Edits team labeling text on Meet Manager report PDFs |

`heat-sheet-stamper` and `dak-malfunction-parser` are subtree-imported from
their original standalone repos (`heatSheetStamper`, `DakMalfunctionParser`,
also present separately under `~/code/`) — check both if you're chasing a
fix that should land in both places.

## Run and test

Each tool is self-contained with its own dependencies and tests — `cd` into
the tool directory and see its README. Python tools use
[uv](https://docs.astral.sh/uv/) (`uv sync`, `uv run`), not `venv`/`pip`.
New Python tools in this repo should follow the same pattern.

## Conventions

- `examples/` at the repo root holds real, publicly-published Meet Manager
  PDFs shared across tools for manual testing and regression tests. Each
  tool also has its own local `examples/` for tool-private samples that
  aren't safe to publish — don't move those into the shared directory.
- Generated PDF outputs from running a tool against shared examples are
  gitignored (`examples/*-sr.pdf`) and shouldn't be committed — regenerate
  instead of tracking.

## Where session memory goes

Don't write commit-by-commit narrative, bug lists, or parser-format detail
into `Projects/*/context.md` or any SealVault `memory/` file. That detail
belongs here — git history and each tool's README. A vault session-close
should log only a one-line pointer: "AOTools: `<topic>`, see git log."
