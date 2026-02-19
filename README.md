# arxiv-to-markdown

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Convert arXiv papers to clean, LLM-readable Markdown format.

**Perfect for:** Researchers feeding papers to LLMs, creating readable documentation, or archiving papers in a searchable format.

---

## Features

- **Author-Year Citations** - Converts numbered citations to `[Author et al., Year](link)` format with clickable arXiv/DOI links
- **LaTeX Math Preservation** - Keeps `$...$` and `$$...$$` math notation for LLM compatibility
- **Separate Appendix Files** - Automatically splits main paper and appendix into separate files
- **Token-Efficient Output** - Simplifies notation (`boldsymbol` → `textbf`, reduces whitespace)
- **Bibliography Generation** - Creates formatted reference list with links
- **Figure Placeholders** - Marks figure locations with captions for LLM context
- **Reference Resolution** - Converts `ref`, `ref` to readable text

---

## Installation

### Prerequisites

- Python 3.9+
- Pandoc 3.0+ (external dependency)

```bash
# macOS
brew install pandoc

# Ubuntu/Debian
sudo apt-get install pandoc

# Other: https://pandoc.org/installing.html
```

### Install

```bash
# Clone and install
git clone <repository-url>
cd arxiv-to-markdown
uv pip install -e .
```

---

## Usage

```bash
# Convert by arXiv ID
arxiv-to-md 2401.12345

# Convert by URL
arxiv-to-md https://arxiv.org/abs/2401.12345

# Specify output directory
arxiv-to-md 2401.12345 -o ./my-papers

# Keep source files (for debugging)
arxiv-to-md 2401.12345 --keep-source -v
```

---

## Output Format

For paper ID `2401.12345`, generates:

```
2401.12345/
├── 2401.12345_main.md       # Main paper content
└── 2401.12345_appendix.md   # Appendix sections (if present)
```

### Citation Example

**Input:**
```latex
\cite{vaswani2017attention} introduced Transformers.
```

**Output:**
```markdown
[Vaswani et al., 2017](https://arxiv.org/abs/1706.03762) introduced Transformers.
```

---

## Architecture

```
arxiv_id
  ↓
downloader.py    →  Download & extract source
  ↓
parser.py        →  Parse LaTeX, expand \input, split document
  ↓
bibtex_handler.py →  Parse bibliography, resolve citations
  ↓
converter.py     →  Convert via Pandoc
  ↓
postprocessor.py →  Clean up markdown
  ↓
Output files     →  {arxiv_id}_main.md + {arxiv_id}_appendix.md
```

---

## Development

```bash
# Run tests
uv run pytest tests/test_comprehensive.py -v

# Install dev dependencies
uv sync
```

See [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md) for architecture details and future improvements.

---

## Known Limitations

1. Some citations may not have links if arXiv ID/DOI not in source
2. Complex LaTeX macros may not convert perfectly
3. Figure images not included (just placeholders)
4. Some author names may parse incorrectly from .bbl files

---

## License

MIT License

---

**Version:** 0.1.0 | **Last Updated:** 2024-02-19
