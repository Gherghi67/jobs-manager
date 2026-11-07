---
name: project-cv-pdf-text
description: "The CV's Source Sans Pro headings lose their word spaces in pypdf and pdftotext -raw; WordSpace=1.3 fixes it, while XeTeXinterwordspaceshaping segfaults Tectonic"
metadata:
  node_type: memory
  type: project
  originSessionId: db6a88df-e7da-497b-96f9-4f9cac2006e0
  modified: 2026-10-12T12:48:33.710Z
---

Found 2026-10-12. In `~/Documents/cv-refactor/latex/cv.pdf` (the file `cv/` serves), every Source Sans Pro run comes out glued in pypdf and `pdftotext -raw`: the name, the job and section headings, `\descript` and `\location`. Examples: "BogdanGherghina", "EREPUBLIKLABS", "April2022". pypdf missed 12 of 19 probe phrases, including every date. pdfminer and default `pdftotext` read the PDF fine, and the Inter body text is fine. The cause is Source Sans Pro's narrow word space; the bundled OTF copies behave the same.

Fix, verified on a scratch build: add `WordSpace=1.3` to the seven Source Sans `\fontspec[Path = …]` calls in `plushcv.cls` (1.15 is not enough). Afterwards all three extractors find every phrase, the page count is unchanged, and the look is the same apart from slightly wider heading word gaps. `\XeTeXinterwordspaceshaping=2` (or `=1`) segfaults Tectonic on the full CV (exit 139), and in a minimal file it only half-works.

A single line does the same job (Draft C, 2026-10-12, word boxes identical to the seven-call version): `\defaultfontfeatures[<font file names>]{WordSpace=1.3}` after `\usepackage{fontspec}`. fontspec matches the bracketed names literally, so `\defaultfontfeatures[\firstnamefont,\secondnamefont]` silently does nothing (pypdf 10/24). Expand them first: `\edef\x{\noexpand\defaultfontfeatures[\firstnamefont,\secondnamefont]}\x{WordSpace=1.3}`.

Column order (checked 2026-10-15): pypdf, pdfminer and `pdftotext -raw` read the whole left column, then the right one. Poppler's default and `-layout` modes interleave them, around Education/Projects (and, before Draft I, the Electronic Arts job too). A reviewer called this an ATS bug; the user chose to keep two columns.

**How to apply:** when building or editing the CV, keep the WordSpace setting and check text extraction (pypdf or `pdftotext -raw` for the name and dates), not only the page count. Applied on 2026-10-12 with Draft C: cv-refactor `~/Documents/cv-refactor/latex/plushcv.cls` now has the one-line `\edef` form. The pre-fix files are kept as `cv.v11.*` and `plushcv.v11.cls`. Related: [[user-work-facts]], [[project-fieldwork]].
