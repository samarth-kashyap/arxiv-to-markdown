# Design Decisions and Future Improvements

**Project:** arxiv-to-markdown  
**Purpose:** Document architectural decisions, design patterns, and roadmap for future development

---

## Architecture Decisions

### 1. Modular Pipeline Design

**Decision:** Split the conversion process into 6 distinct modules (downloader, parser, bibtex_handler, converter, postprocessor, cli)

**Rationale:**
- Each module has a single, well-defined responsibility
- Easier to test, debug, and maintain independently
- Allows for individual module improvements without affecting others
- Clear error attribution (module-specific exceptions)

**Trade-offs:**
- + Separation of concerns
- + Easier unit testing
- - Slightly more complex orchestration in cli.py
- - Cross-module dependencies require careful interface design

---

### 2. Pandoc Dependency

**Decision:** Use Pandoc as the LaTeX→Markdown converter instead of building a native parser

**Rationale:**
- LaTeX parsing is extremely complex (Turing-complete language)
- Pandoc handles 95% of LaTeX constructs correctly
- Industry standard, actively maintained

**Trade-offs:**
- + Handles edge cases we'd never anticipate
- + Regular updates for new LaTeX packages
- - External dependency users must install
- - Less control over output format
- - Some LaTeX constructs Pandoc can't handle

**Mitigation:**
- Pre-process known problematic commands in converter.py
- Post-process Pandoc output for LLM optimization

---

### 3. Regex-Based LaTeX Parsing

**Decision:** Use regex for LaTeX structure parsing (\input expansion, citation extraction, label detection)

**Rationale:**
- Full LaTeX parsing would require implementing TeX engine
- For our use case (structure extraction), regex is "good enough"
- Performance is acceptable for typical papers (2-10s conversion)

**Trade-offs:**
- + Simple and fast to implement
- + Works for 90% of papers
- - Regex can't handle nested structures perfectly
- - Some edge cases will fail
- - "You can't parse HTML/LaTeX with regex" (but we do it anyway)

**Key Patterns Used:**
```python
# Circular include detection
_processed_files: Set[str] = set()

# Negative lookbehind to avoid matching commented commands
input_pattern = r'(?<!%)\\(input|include)\{([^}]+)\}'

# Iterative expansion with depth limit
for _ in range(max_iterations):
    new_content = re.sub(input_pattern, expand_input, content)
```

---

### 4. Custom Exception Classes

**Decision:** Each module defines its own exception class (ArxivDownloadError, LaTeXParserError, etc.)

**Rationale:**
- Clear error attribution
- Allows granular error handling in CLI
- Makes debugging easier

**Pattern:**
```python
class ArxivDownloadError(Exception):
    """Custom exception for arXiv download failures."""
    pass
```

---

### 5. Author-Year Citation Format

**Decision:** Convert numbered citations to author-year format with markdown links

**Rationale:**
- LLMs prefer natural language over numbers
- Links provide context for human readers
- Standard academic format

**Implementation:**
- Priority: .bbl file → .bib file → arXiv API lookup → placeholder
- Handles various author formats: "John Smith", "Smith, John", "van der Waals"
- Generates markdown links from arXiv IDs or DOIs

---

### 6. Temp File Management

**Decision:** Use context managers and explicit cleanup for temp files

**Rationale:**
- Safety: files cleaned up even on errors
- Predictable: no temp file pollution
- Debugging: `--keep-source` flag preserves files

**Pattern:**
```python
with tempfile.NamedTemporaryFile(mode='w', suffix='.tex', delete=False) as tmp:
    tmp.write(content)
    tmp_path = tmp.name
try:
    # Process file
finally:
    Path(tmp_path).unlink(missing_ok=True)
```

---

## Key Challenges & Solutions

### Challenge 1: Circular \input Includes

**Problem:** Papers can have circular \input commands causing infinite recursion

**Solution:**
- Track processed files in a Set
- Maximum depth limit (default 20)
- Return placeholder comment for circular references

```python
file_key = str(tex_path.resolve())
if file_key in self._processed_files:
    return f"% Circular include skipped: {tex_path.name}\n"
```

### Challenge 2: Multi-line \author Blocks

**Problem:** \author{} can span 50+ lines with nested braces

**Solution:**
- Don't preprocess \author at all
- Let Pandoc handle it (it does this well)
- Remove only simple commands like \title, \date

### Challenge 3: Author Name Parsing

**Problem:** Various formats: "John Smith", "Smith, John", "van der Waals, J.D."

**Solution:**
```python
def _extract_last_name(self, author: str) -> str:
    if ',' in author:
        # "Last, First" format
        return author.split(',')[0].strip()
    else:
        # Check for particles: van, de, der, etc.
        particles = ['van', 'de', 'der', ...]
        if len(parts) >= 3 and parts[-2].lower() in particles:
            return f"{parts[-2]} {parts[-1]}"
        return parts[-1]
```

### Challenge 4: Pandoc Exit Code 64

**Problem:** Pandoc crashes with cryptic error messages

**Common Causes:**
- Unmatched braces
- Stray `}` outside environments
- Complex command definitions with #1, #2 parameters

**Solution:**
- Pre-process: Remove problematic commands in converter.py
- Debug pattern: Save input to `/tmp/debug_input.tex` before conversion
- Manual test: `pandoc /tmp/debug_input.tex -f latex -t markdown`

---

## Performance Considerations

### Current Metrics
- **Typical conversion time:** 2-10 seconds per paper
- **Network time:** 1-2 seconds (arXiv download)
- **Memory usage:** ~5-50MB depending on paper size
- **Output size:** ~10-500KB markdown files

### Bottlenecks
1. **ArXiv API calls** - Network latency, rate limiting
2. **Pandoc conversion** - 0.5-1s per document
3. **Regex on large files** - Can be slow on >1MB papers

### Optimization Opportunities
- Cache arXiv API results
- Parallel citation processing
- Lazy evaluation

---

## Testing Strategy

### Current Coverage (41 tests)
- **TestExtractArxivId** (6 tests) - ID format variations
- **TestLaTeXParser** (8 tests) - Parsing edge cases
- **TestCitation** (8 tests) - Author formatting
- **TestBibliographyHandler** (5 tests) - BBL/BIB parsing
- **TestLaTeXConverter** (5 tests) - Conversion edge cases
- **TestMarkdownPostProcessor** (5 tests) - Post-processing
- **TestIntegration** (1 test) - Full pipeline
- **TestEdgeCases** (3 tests) - Unicode, empty sections

### Testing Philosophy
1. Test behavior, not implementation
2. Use temp directories, don't touch real filesystem
3. Clean up in fixtures, not tests
4. Parametrize similar tests

### Recommended Test Papers
- `1706.03762` - "Attention Is All You Need" (complex but works)
- Papers with appendices
- Papers with figures and tables
- Papers with complex math

---

## Future Improvements

### Short Term (Next 1-2 weeks)

- [ ] **Better Figure Handling**
  - Extract captions from figure environments
  - Better placeholder formatting
  - Option to download actual figure images

- [ ] **Progress Bars**
  - Show progress for long operations
  - Useful for papers with many citations

- [ ] **Citation Caching**
  - Cache arXiv API results locally
  - Avoid repeated lookups for same papers

- [ ] **Support .tex.gz Files**
  - Some arXiv papers use gzipped source

### Medium Term (1-2 months)

- [ ] **Parallel Citation Processing**
  - Look up multiple citations concurrently
  - Reduce conversion time for citation-heavy papers

- [ ] **Support Other Archives**
  - bioRxiv, medRxiv, etc.
  - Similar source format

- [ ] **Web UI (Streamlit)**
  - Simple web interface
  - Drag-and-drop arXiv ID
  - Preview before download

- [ ] **Docker Container**
  - Include Pandoc in container
  - One-command deployment
  - Consistent environment

- [ ] **Table Extraction**
  - Convert LaTeX tables to markdown tables
  - Handle complex multi-column tables

### Long Term (3+ months)

- [ ] **Native LaTeX Parser**
  - Remove Pandoc dependency
  - Better control over output
  - Handle edge cases Pandoc misses

- [ ] **Figure Extraction & OCR**
  - Extract actual figure images
  - OCR for text in figures
  - Generate figure descriptions

- [ ] **Automatic Summarization**
  - Generate paper summaries
  - Extract key findings
  - Create structured abstracts

- [ ] **Citation Network Analysis**
  - Build citation graphs
  - Find related papers
  - Suggest similar research

- [ ] **Multi-format Output**
  - JSON structured output
  - Plain text (no markdown)
  - LaTeX (round-trip conversion)

---

## Maintenance Tips

### Regular Tasks
1. Update dependencies: `uv sync --upgrade`
2. Run tests: `uv run pytest`
3. Test with real papers: Try different arXiv IDs
4. Check for deprecation warnings

### When Things Break
1. Check if arXiv API changed
2. Check if Pandoc version changed
3. Look for new LaTeX package usage in papers
4. Check if bibtexparser has issues

### Adding New Features
1. Write test first (TDD)
2. Update documentation
3. Add example to README
4. Update this file

---

## Resources

### LaTeX Parsing
- **TeXbook** - Knuth's original (authoritative)
- **LaTeX2e sources** - See how real LaTeX works
- **Pandoc sources** - See how they handle LaTeX

### Regex
- **regex101.com** - Test and debug regex
- **Python re docs** - https://docs.python.org/3/library/re.html
- **"Mastering Regular Expressions"** by Friedl

### ArXiv
- **API docs:** https://arxiv.org/help/api
- **Bulk data:** https://arxiv.org/help/bulk_data

### UV Package Manager
- Always use `uv run` instead of activating venv
- `.venv` is auto-created
- `uv.lock` locks exact versions - commit to git

---

## Random Tips for Future Self

1. **Always use raw strings** for regex: `r'\pattern'` not `'\pattern'`
2. **Use re.VERBOSE** for complex regex with comments
3. **Don't parse HTML/LaTeX with regex**... but we have to here
4. **Log everything** in verbose mode
5. **Save intermediate files** when debugging
6. **Test with "Attention is All You Need"** - it's complex but works
7. **Unicode is your friend** until it's not
8. **Temp files are your friend** until you forget to clean up
9. **Pandoc is magic** until it isn't
10. **Users will find edge cases** you never imagined

---

**Remember:** The goal is converting papers to markdown, not writing a perfect LaTeX parser. Good enough is good enough.

**Last Updated:** 2024-02-19  
**Version:** 0.1.0
