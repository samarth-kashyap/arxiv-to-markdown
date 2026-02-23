# arxiv-to-markdown

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Convert arXiv papers from LaTeX to clean, readable Markdown optimized for LLM consumption.

## Features

- **Equation Cross-References** - Converts `\ref{eq:label}` to `[(eq:label)](#eq:label)` with clickable anchors
- **Author-Year Citations** - Transforms `\cite{key}` to `[Author et al., Year](link)` format with arXiv/DOI links
- **LaTeX Math Preservation** - Keeps `$...$` and `$$...$$` notation for compatibility with math renderers
- **Bibliography Generation** - Creates formatted reference sections from `.bbl` or `.bib` files
- **Appendix Separation** - Automatically splits main content and appendix into separate files
- **Figure Placeholders** - Marks figure locations with captions for context
- **Clean Output** - Removes LaTeX artifacts, simplifies notation, optimizes for token efficiency

## Installation

### Prerequisites

- Python 3.9+
- Pandoc 3.0+ (system package)

```bash
# macOS
brew install pandoc

# Ubuntu/Debian
sudo apt-get install pandoc

# Other systems: https://pandoc.org/installing.html
```

### Install

```bash
# Clone the repository
git clone <repository-url>
cd arxiv-to-markdown

# Install with uv (recommended)
uv pip install -e .

# Or with pip
pip install -e .
```

## Usage

```bash
# Convert by arXiv ID
arxiv-to-md 2401.12345

# Convert by URL
arxiv-to-md https://arxiv.org/abs/2401.12345

# Specify output directory
arxiv-to-md 2401.12345 -o ./papers

# Keep source files for debugging
arxiv-to-md 2401.12345 --keep-source -v
```

## Output

For paper ID `2401.12345`, creates:

```
2401.12345/
├── 2401.12345_main.md       # Main paper content
└── 2401.12345_appendix.md   # Appendix (if present)
```

## Examples

### Equation References

**Input (LaTeX):**
```latex
\begin{equation}
E = mc^2
\label{eq:energy}
\end{equation}

As shown in Eq.~\ref{eq:energy}...
```

**Output (Markdown):**
```markdown
$$
E = mc^2
$$ <a name="eq:energy"></a>

As shown in Equation [(eq:energy)](#eq:energy)...
```

### Citations

**Input (LaTeX):**
```latex
\cite{vaswani2017attention} introduced Transformers.
```

**Output (Markdown):**
```markdown
[Vaswani et al., 2017](https://arxiv.org/abs/1706.03762) introduced Transformers.
```

## Architecture

```
arXiv ID
  ↓
downloader.py     →  Download & extract source
  ↓
parser.py         →  Parse LaTeX, expand \input{}, identify equation labels
  ↓
bibtex_handler.py →  Parse bibliography, resolve citations
  ↓
converter.py      →  Convert via Pandoc, add equation anchors & refs
  ↓
postprocessor.py  →  Clean up markdown, simplify math
  ↓
Output files      →  {arxiv_id}_main.md + {arxiv_id}_appendix.md
```

## Development

```bash
# Run tests
uv run pytest tests/ -v

# Install dev dependencies
uv sync
```

### Project Structure

```
arxiv-to-markdown/
├── arxiv_to_md/
│   ├── __init__.py
│   ├── cli.py              # Command-line interface
│   ├── converter.py        # LaTeX → Markdown conversion
│   ├── postprocessor.py    # Markdown cleanup
│   ├── downloader.py       # arXiv source download
│   ├── parser.py           # LaTeX structure parsing
│   └── bibtex_handler.py   # Bibliography processing
├── tests/
│   └── test_comprehensive.py
├── pyproject.toml
└── README.md
```

## How It Works

### Equation Labeling

Unlike other converters that guess equation numbers (which is fragile and often wrong), this tool uses the **actual LaTeX labels** for cross-references:

1. **Parser** identifies which `\label{}` commands appear inside equation environments
2. **Converter** replaces `\label{foo}` with `<a name="foo"></a>`
3. **Converter** replaces `\ref{foo}` or `\eqref{foo}` with `[(foo)](#foo)`

This approach is:
- ✅ 100% accurate (uses author's exact labels)
- ✅ Works with any naming convention (`eq:foo`, `opt_problem`, etc.)
- ✅ Handles unnumbered equations, subequations, manual tags
- ✅ No LaTeX compilation required

### Citation Resolution

1. Parse `.bbl` file (if available) to extract author/year/title/URLs
2. Look up missing citations via arXiv API
3. Format as `[Author et al., Year](link)` with arXiv or DOI links

## Limitations

- Figure images are not included (only placeholders with captions)
- Complex LaTeX macros may not convert perfectly
- Some table formatting may be simplified
- Citations without arXiv ID or DOI in source won't have links

## License

MIT License

## Acknowledgments

Built with:
- [Pandoc](https://pandoc.org/) for LaTeX→Markdown conversion
- [arxiv](https://pypi.org/project/arxiv/) library for arXiv API access
- [pypandoc](https://pypi.org/project/pypandoc/) for Pandoc Python bindings
