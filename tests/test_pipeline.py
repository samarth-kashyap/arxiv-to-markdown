#!/usr/bin/env python3
"""Test script for arxiv-to-markdown conversion."""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from arxiv_to_md.parser import LaTeXParser
from arxiv_to_md.bibtex_handler import BibliographyHandler, Citation
from arxiv_to_md.converter import LaTeXConverter
from arxiv_to_md.postprocessor import MarkdownPostProcessor

# Create a sample .bbl file
sample_bbl = r"""\begin{thebibliography}{10}

\bibitem{smith2020attention}
J. Smith, A. Jones, and B. Lee.
\newblock Attention mechanisms in neural networks.
\newblock In {\\em Proceedings of NeurIPS}, 2020.

\bibitem{vaswani2017transformer}
A. Vaswani, N. Shazeer, N. Parmar, J. Uszkoreit, L. Jones, A. Gomez, L. Kaiser, and I. Polosukhin.
\newblock Attention is all you need.
\newblock In {\\em Advances in Neural Information Processing Systems}, pages 5998--6008, 2017.

\end{thebibliography}
"""

# Test the pipeline
test_file = Path(__file__).parent / "sample_paper.tex"
if not test_file.exists():
    print(f"Error: {test_file} not found")
    sys.exit(1)

print("=" * 60)
print("Testing arxiv-to-markdown pipeline")
print("=" * 60)

# Step 1: Parse LaTeX
print("\n1. Parsing LaTeX structure...")
parser = LaTeXParser(test_file)
main_content, appendix_content, _ = parser.split_document()
print(f"   - Found {len(parser.labels)} labels")
print(f"   - Main content: {len(main_content)} chars")
print(f"   - Appendix: {'Yes' if appendix_content else 'No'}")

# Step 2: Handle bibliography
print("\n2. Processing bibliography...")
# Create temp bbl file
bbl_path = test_file.parent / "sample.bbl"
bbl_path.write_text(sample_bbl)

bib_handler = BibliographyHandler(bbl_path=bbl_path)
print(f"   - Found {len(bib_handler.citations)} citations")
for key in bib_handler.citations:
    cite = bib_handler.citations[key]
    print(f"     - {key}: {cite.format_author_year()}")

# Step 3: Convert to markdown
print("\n3. Converting to markdown...")
converter = LaTeXConverter(bib_handler)
md_content = converter.convert(main_content)
print(f"   - Markdown: {len(md_content)} chars")

# Step 4: Post-process
print("\n4. Post-processing...")
postprocessor = MarkdownPostProcessor()
bibliography = bib_handler.generate_bibliography()
final_content = postprocessor.process(md_content, bibliography)
print(f"   - Final: {len(final_content)} chars")

# Step 5: Save output
print("\n5. Saving output...")
output_file = test_file.parent / "sample_output.md"
output_file.write_text(final_content)
print(f"   - Saved to: {output_file}")

print("\n" + "=" * 60)
print("Preview (first 1000 chars):")
print("=" * 60)
print(final_content[:1000])
print("\n...")

# Cleanup
bbl_path.unlink()
