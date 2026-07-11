# Shared examples

Real, publicly-published HY-TEK Meet Manager PDFs used across tools for
manual testing, documentation screenshots, and automated regression tests.

| File | Source |
|---|---|
| `ngsl-invitational-2022.pdf` | 2022 NGSL Invitational Meet, morning session |
| `osaa-state-championships-2026-finals.pdf` | 2026 OSAA 6A Swimming State Championships, finals |
| `osaa-state-championships-2024-prelims.pdf` | 2024 OSAA 4A/3A/2A/1A Swimming State Championships, preliminaries |

These three files intentionally cover different Meet Manager export shapes
for the same visual header layout (team name + "Page N", top-left of every
page) — e.g. the 2024 prelims file packs the team name and page text into a
single content-stream operator with a large kerning-style gap, while the
other two draw them as two separate operators. Keeping both shapes in the
regression suite is what caught that difference in the first place.

Used by:

- [../heat-sheet-stamper/](../heat-sheet-stamper/) — stamps DQ/NS/DFS overlays; doesn't touch existing text, so any PDF works, but these are the tracked regression fixtures
- [../meet-report-formatter/](../meet-report-formatter/) — erases the header team-name text; these files exercise both content-stream shapes above

Each tool's own `examples/` directory (not this one) holds tool-private
sample files that aren't safe to publish — e.g. real team-fee/entry reports
with swimmers' names, ages, and times. Only add files here if they're
confirmed public (a published meet program, results page, etc.).
