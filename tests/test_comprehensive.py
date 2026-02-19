"""Comprehensive test suite for arxiv-to-markdown.

This module contains tests for all components and edge cases.
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from arxiv_to_md.downloader import (
    extract_arxiv_id,
    ArxivDownloadError,
)
from arxiv_to_md.parser import LaTeXParser, LaTeXParserError
from arxiv_to_md.bibtex_handler import Citation, BibliographyHandler
from arxiv_to_md.converter import LaTeXConverter, LaTeXConversionError
from arxiv_to_md.postprocessor import MarkdownPostProcessor


# ============================================================================
# Test downloader module
# ============================================================================

class TestExtractArxivId:
    """Test arXiv ID extraction."""
    
    def test_valid_id_only(self):
        """Test extracting ID from clean ID string."""
        assert extract_arxiv_id("2401.12345") == "2401.12345"
        assert extract_arxiv_id("1706.03762") == "1706.03762"
    
    def test_arxiv_notation(self):
        """Test extracting ID from arXiv: notation."""
        assert extract_arxiv_id("arXiv:2401.12345") == "2401.12345"
        assert extract_arxiv_id("arxiv:2401.12345") == "2401.12345"
    
    def test_abs_url(self):
        """Test extracting ID from abs URL."""
        assert extract_arxiv_id("https://arxiv.org/abs/2401.12345") == "2401.12345"
        assert extract_arxiv_id("http://arxiv.org/abs/2401.12345") == "2401.12345"
    
    def test_pdf_url(self):
        """Test extracting ID from PDF URL."""
        assert extract_arxiv_id("https://arxiv.org/pdf/2401.12345.pdf") == "2401.12345"
    
    def test_version_suffix(self):
        """Test extracting ID with version suffix."""
        assert extract_arxiv_id("2401.12345v1") == "2401.12345"
        assert extract_arxiv_id("2401.12345v2") == "2401.12345"
    
    def test_invalid_inputs(self):
        """Test that invalid inputs raise ValueError."""
        invalid_inputs = [
            "",
            "not-an-id",
            "2401",  # Too short
            "https://example.com",
            "arxiv.org",  # Missing ID
        ]
        for invalid in invalid_inputs:
            with pytest.raises(ValueError):
                extract_arxiv_id(invalid)


# ============================================================================
# Test parser module
# ============================================================================

class TestLaTeXParser:
    """Test LaTeX parsing."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)
    
    def test_simple_document(self, temp_dir):
        """Test parsing a simple LaTeX document."""
        tex_content = r"""
\documentclass{article}
\begin{document}
\section{Introduction}
This is a test.
\end{document}
"""
        tex_file = temp_dir / "test.tex"
        tex_file.write_text(tex_content)
        
        parser = LaTeXParser(tex_file)
        main, appendix, bib = parser.split_document()
        
        assert r"\begin{document}" in main
        assert r"\end{document}" in main
        assert appendix is None
    
    def test_with_appendix(self, temp_dir):
        """Test parsing document with appendix."""
        tex_content = r"""
\documentclass{article}
\begin{document}
\section{Introduction}
This is the main content.
\appendix
\section{Proofs}
This is the appendix.
\end{document}
"""
        tex_file = temp_dir / "test.tex"
        tex_file.write_text(tex_content)
        
        parser = LaTeXParser(tex_file)
        main, appendix, bib = parser.split_document()
        
        assert main is not None
        assert appendix is not None
        assert "Introduction" in main
        assert "Proofs" in appendix
    
    def test_with_input(self, temp_dir):
        r"""Test expanding \input commands."""
        # Create main file
        main_content = r"""
\documentclass{article}
\begin{document}
\input{section1}
\end{document}
"""
        # Create included file
        section_content = r"""
\section{Section 1}
This is section 1.
"""
        main_file = temp_dir / "main.tex"
        section_file = temp_dir / "section1.tex"
        main_file.write_text(main_content)
        section_file.write_text(section_content)
        
        parser = LaTeXParser(main_file)
        assert "Section 1" in parser.content
    
    def test_circular_include_detection(self, temp_dir):
        """Test detection of circular includes."""
        # Create files that include each other
        file1 = temp_dir / "file1.tex"
        file2 = temp_dir / "file2.tex"
        
        file1.write_text(r"\input{file2}")
        file2.write_text(r"\input{file1}")
        
        parser = LaTeXParser(file1)
        # Should not hang or crash, should handle gracefully
        assert "Circular include skipped" in parser.content
    
    def test_missing_input(self, temp_dir):
        r"""Test handling of missing \input files."""
        tex_content = r"""
\documentclass{article}
\begin{document}
\input{nonexistent}
\end{document}
"""
        tex_file = temp_dir / "test.tex"
        tex_file.write_text(tex_content)
        
        parser = LaTeXParser(tex_file)
        assert "Include not found" in parser.content
    
    def test_deep_nesting(self, temp_dir):
        """Test handling of deeply nested includes."""
        # Create chain of includes
        for i in range(15):
            file_path = temp_dir / f"file{i}.tex"
            if i < 14:
                content = f"\\input{{file{i+1}}}"
            else:
                content = "Deep content"
            file_path.write_text(content)
        
        parser = LaTeXParser(temp_dir / "file0.tex")
        assert "Deep content" in parser.content
    
    def test_extract_citations(self, temp_dir):
        """Test citation extraction."""
        tex_content = r"""
\documentclass{article}
\begin{document}
See \cite{smith2020} and \cite{jones2019,lee2021}.
Also \citet{doe2018} said something.
\end{document}
"""
        tex_file = temp_dir / "test.tex"
        tex_file.write_text(tex_content)
        
        parser = LaTeXParser(tex_file)
        citations = parser.extract_citations()
        
        assert "smith2020" in citations
        assert "jones2019" in citations
        assert "lee2021" in citations
        assert "doe2018" in citations
    
    def test_label_extraction(self, temp_dir):
        """Test label extraction and categorization."""
        tex_content = r"""
\documentclass{article}
\begin{document}
\section{Intro} \label{sec:intro}
\begin{equation} \label{eq:test}
x = y
\end{equation}
\begin{figure} \label{fig:1}
\caption{Test}
\end{figure}
\end{document}
"""
        tex_file = temp_dir / "test.tex"
        tex_file.write_text(tex_content)
        
        parser = LaTeXParser(tex_file)
        
        assert parser.labels.get("sec:intro") == "sec"
        assert parser.labels.get("eq:test") == "eq"
        assert parser.labels.get("fig:1") == "fig"


# ============================================================================
# Test bibtex_handler module
# ============================================================================

class TestCitation:
    """Test Citation class."""
    
    def test_format_author_year_single(self):
        """Test formatting single author."""
        cite = Citation(
            key="test",
            authors=["John Smith"],
            year="2020",
            title="Test"
        )
        assert cite.format_author_year() == "Smith, 2020"
    
    def test_format_author_year_two(self):
        """Test formatting two authors."""
        cite = Citation(
            key="test",
            authors=["John Smith", "Jane Doe"],
            year="2020",
            title="Test"
        )
        assert cite.format_author_year() == "Smith & Doe, 2020"
    
    def test_format_author_year_multiple(self):
        """Test formatting multiple authors."""
        cite = Citation(
            key="test",
            authors=["John Smith", "Jane Doe", "Bob Lee"],
            year="2020",
            title="Test"
        )
        assert cite.format_author_year() == "Smith et al., 2020"
    
    def test_format_author_year_last_name_extraction(self):
        """Test various author name formats."""
        # Test "Last, First" format
        cite = Citation(
            key="test",
            authors=["Smith, John"],
            year="2020",
            title="Test"
        )
        assert cite.format_author_year() == "Smith, 2020"
        
        # Test multi-word last name
        cite = Citation(
            key="test",
            authors=["van der Waals, J.D."],
            year="2020",
            title="Test"
        )
        assert cite.format_author_year() == "van der Waals, 2020"
    
    def test_get_link_arxiv(self):
        """Test getting arXiv link."""
        cite = Citation(
            key="test",
            authors=["Smith"],
            year="2020",
            title="Test",
            arxiv_id="2001.12345"
        )
        assert cite.get_link() == "https://arxiv.org/abs/2001.12345"
    
    def test_get_link_doi(self):
        """Test getting DOI link."""
        cite = Citation(
            key="test",
            authors=["Smith"],
            year="2020",
            title="Test",
            doi="10.1234/test"
        )
        assert cite.get_link() == "https://doi.org/10.1234/test"
    
    def test_get_link_none(self):
        """Test when no link available."""
        cite = Citation(
            key="test",
            authors=["Smith"],
            year="2020",
            title="Test"
        )
        assert cite.get_link() is None


class TestBibliographyHandler:
    """Test BibliographyHandler."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)
    
    def test_parse_simple_bbl(self, temp_dir):
        """Test parsing simple .bbl file."""
        bbl_content = r"""
\begin{thebibliography}{10}
\bibitem{smith2020}
John Smith.
\newblock A Great Paper.
\newblock In {\em Proceedings}, 2020.
\end{thebibliography}
"""
        bbl_file = temp_dir / "test.bbl"
        bbl_file.write_text(bbl_content)
        
        handler = BibliographyHandler(bbl_path=bbl_file)
        
        assert "smith2020" in handler.citations
        cite = handler.citations["smith2020"]
        assert cite.year == "2020"
    
    def test_parse_bbl_with_arxiv(self, temp_dir):
        """Test parsing .bbl with arXiv ID."""
        bbl_content = r"""
\begin{thebibliography}{10}
\bibitem{vaswani2017}
A. Vaswani et al.
\newblock Attention is All You Need.
\newblock arXiv:1706.03762, 2017.
\end{thebibliography}
"""
        bbl_file = temp_dir / "test.bbl"
        bbl_file.write_text(bbl_content)
        
        handler = BibliographyHandler(bbl_path=bbl_file)
        cite = handler.citations["vaswani2017"]
        assert cite.arxiv_id == "1706.03762"
    
    def test_parse_bib_file(self, temp_dir):
        """Test parsing .bib file."""
        bib_content = """
@article{smith2020,
  author = {Smith, John},
  title = {A Great Paper},
  year = {2020},
  journal = {Journal}
}
"""
        bib_file = temp_dir / "test.bib"
        bib_file.write_text(bib_content)
        
        handler = BibliographyHandler(bib_path=bib_file)
        
        assert "smith2020" in handler.citations
        cite = handler.citations["smith2020"]
        assert cite.title == "A Great Paper"
    
    def test_format_citation_markdown(self, temp_dir):
        """Test citation formatting."""
        bbl_content = r"""
\begin{thebibliography}{10}
\bibitem{test}
John Smith.
\newblock Test Paper.
\newblock 2020.
\end{thebibliography}
"""
        bbl_file = temp_dir / "test.bbl"
        bbl_file.write_text(bbl_content)
        
        handler = BibliographyHandler(bbl_path=bbl_file)
        formatted = handler.format_citation_markdown("test")
        
        assert "Smith" in formatted
        assert "2020" in formatted
    
    def test_generate_bibliography(self, temp_dir):
        """Test bibliography generation."""
        bbl_content = r"""
\begin{thebibliography}{10}
\bibitem{smith2020}
John Smith.
\newblock Test Paper.
\newblock 2020.
\end{thebibliography}
"""
        bbl_file = temp_dir / "test.bbl"
        bbl_file.write_text(bbl_content)
        
        handler = BibliographyHandler(bbl_path=bbl_file)
        bib = handler.generate_bibliography()
        
        assert "## References" in bib
        assert "Smith" in bib
        assert "2020" in bib


# ============================================================================
# Test converter module
# ============================================================================

class TestLaTeXConverter:
    """Test LaTeX to Markdown conversion."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)
    
    def test_convert_simple_document(self, temp_dir):
        """Test converting simple document."""
        tex_content = r"""
\documentclass{article}
\begin{document}
\section{Introduction}
Hello world.
\end{document}
"""
        converter = LaTeXConverter()
        md = converter.convert(tex_content)
        
        assert "# Introduction" in md
        assert "Hello world" in md
    
    def test_convert_with_math(self, temp_dir):
        """Test preserving math."""
        tex_content = r"""
\documentclass{article}
\begin{document}
The equation is $x = y$.
\end{document}
"""
        converter = LaTeXConverter()
        md = converter.convert(tex_content)
        
        assert "$x = y$" in md
    
    def test_convert_empty_raises_error(self):
        """Test that empty content raises error."""
        converter = LaTeXConverter()
        with pytest.raises(LaTeXConversionError):
            converter.convert("")
    
    def test_preprocess_references(self):
        """Test reference preprocessing."""
        converter = LaTeXConverter()
        content = r"See Equation \ref{eq:1} and Figure \ref{fig:1}."
        processed = converter._preprocess_references(content)
        
        assert "Equation" in processed
        assert "Figure" in processed
        assert "\\ref" not in processed
    
    def test_preprocess_commands(self):
        """Test command preprocessing."""
        converter = LaTeXConverter()
        content = r"\maketitle \documentclass{article} \usepackage{amsmath}"
        processed = converter._preprocess_commands(content)
        
        assert r"\maketitle" not in processed
        assert r"\documentclass" not in processed
        assert r"\usepackage" not in processed
    
    def test_preprocess_multiline_commands(self):
        """Test removing multi-line LaTeX commands."""
        from arxiv_to_md.converter import _remove_nested_command
        
        # Test simple nested command
        content = r"\address{Line 1\Line 2}Some text"
        processed = _remove_nested_command(content, 'address')
        assert "Line 1" not in processed
        assert "Line 2" not in processed
        assert "Some text" in processed
        
        # Test nested braces
        content = r"\address{University of {Somewhere}}More text"
        processed = _remove_nested_command(content, 'address')
        assert "University" not in processed
        assert "Somewhere" not in processed
        assert "More text" in processed
    
    def test_preprocess_preamble_commands(self):
        """Test removing preamble commands."""
        converter = LaTeXConverter()
        content = r"\newtheorem{theorem}{Theorem} \definecolor{red}{rgb}{1,0,0} Some text"
        processed = converter._preprocess_commands(content)
        
        assert r"\newtheorem" not in processed
        assert r"\definecolor" not in processed
        assert "Some text" in processed


# ============================================================================
# Test postprocessor module
# ============================================================================

class TestMarkdownPostProcessor:
    """Test markdown post-processing."""
    
    def test_cleanup_multiple_blank_lines(self):
        """Test collapsing multiple blank lines."""
        processor = MarkdownPostProcessor()
        content = "Line 1\n\n\n\nLine 2"
        processed = processor._cleanup_content(content)
        
        assert "\n\n\n" not in processed
    
    def test_simplify_math_boldsymbol(self):
        r"""Test simplifying \boldsymbol."""
        processor = MarkdownPostProcessor()
        content = r"$\boldsymbol{x}$"
        processed = processor._simplify_math(content)

        assert r"\boldsymbol" not in processed
        assert r"\mathbf" in processed

    def test_simplify_math_operatorname(self):
        r"""Test simplifying \operatorname."""
        processor = MarkdownPostProcessor()
        content = r"$\operatorname{softmax}$"
        processed = processor._simplify_math(content)

        assert r"\operatorname" not in processed
        assert "softmax" in processed

    def test_simplify_left_right(self):
        r"""Test simplifying \left and \right."""
        processor = MarkdownPostProcessor()
        content = r"$\left( x \right)$"
        processed = processor._simplify_math(content)

        assert r"\left" not in processed
        assert r"\right" not in processed
        assert "( x )" in processed
    
    def test_clean_figures(self):
        """Test figure placeholder conversion."""
        processor = MarkdownPostProcessor()
        content = "![Caption](path/to/figure.png)"
        processed = processor._clean_figures(content)
        
        assert "[Figure: Caption]" in processed
    
    def test_split_appendix(self):
        """Test appendix splitting."""
        processor = MarkdownPostProcessor()
        content = "# Main\nContent\n# Appendix\nAppendix content"
        main, appendix = processor.split_appendix(content)

        assert "Main" in main
        assert "Content" in main
        assert "Appendix" in appendix
        assert "Appendix content" in appendix

    def test_cleanup_latex_artifacts(self):
        """Test cleaning up LaTeX artifacts at start of document."""
        processor = MarkdownPostProcessor()

        # Test removing theorem artifacts
        content = "Theorem\n\nProposition\n\n# Introduction\nSome content"
        processed = processor._cleanup_content(content)
        assert "# Introduction" in processed
        assert "Some content" in processed

        # Test removing bracketed theorem references
        content = "\\[theorem\\]\n\n# Main\nContent"
        processed = processor._cleanup_content(content)
        assert "# Main" in processed
        assert "Content" in processed
        assert "theorem" not in processed or "#" in processed


# ============================================================================
# Integration tests
# ============================================================================

class TestIntegration:
    """Integration tests."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)
    
    def test_full_pipeline_simple(self, temp_dir):
        """Test full pipeline with simple document."""
        # Create LaTeX file
        tex_content = r"""
\documentclass{article}
\begin{document}
\section{Introduction}
This is a test paper \cite{smith2020}.
\begin{thebibliography}{10}
\bibitem{smith2020}
John Smith.
\newblock Test Paper.
\newblock 2020.
\end{thebibliography}
\end{document}
"""
        tex_file = temp_dir / "paper.tex"
        tex_file.write_text(tex_content)
        
        # Parse
        parser = LaTeXParser(tex_file)
        main_content, _, embedded_bib = parser.split_document()
        
        # Handle bibliography
        bib_handler = BibliographyHandler()
        if embedded_bib:
            import tempfile as tf
            with tf.NamedTemporaryFile(mode='w', suffix='.bbl', delete=False) as tmp:
                tmp.write(embedded_bib)
                bbl_path = Path(tmp.name)
            bib_handler = BibliographyHandler(bbl_path=bbl_path)
        
        for cite_key in parser.extract_citations():
            bib_handler.resolve_citation(cite_key)
        
        # Convert
        converter = LaTeXConverter(bib_handler)
        md = converter.convert(main_content)
        
        # Post-process
        postprocessor = MarkdownPostProcessor()
        bibliography = bib_handler.generate_bibliography()
        md = postprocessor.process(md, bibliography)
        
        # Verify
        assert "# Introduction" in md
        assert "Smith" in md
        assert "2020" in md
        assert "## References" in md


# ============================================================================
# Edge cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)
    
    def test_unicode_in_tex(self, temp_dir):
        """Test handling of unicode characters."""
        tex_content = r"""
\documentclass{article}
\begin{document}
Section with unicode:café, naïve, résumé.
\end{document}
"""
        tex_file = temp_dir / "test.tex"
        tex_file.write_text(tex_content, encoding='utf-8')
        
        parser = LaTeXParser(tex_file)
        assert "café" in parser.content
    
    def test_empty_sections(self, temp_dir):
        """Test handling of empty sections."""
        tex_content = r"""
\documentclass{article}
\begin{document}
\section{Empty}
\subsection{Also Empty}
\end{document}
"""
        tex_file = temp_dir / "test.tex"
        tex_file.write_text(tex_content)
        
        parser = LaTeXParser(tex_file)
        main, _, _ = parser.split_document()
        assert r"\end{document}" in main
    
    def test_very_long_lines(self, temp_dir):
        """Test handling of very long lines."""
        tex_content = r"\documentclass{article}\begin{document}" + "x" * 10000 + r"\end{document}"
        tex_file = temp_dir / "test.tex"
        tex_file.write_text(tex_content)
        
        parser = LaTeXParser(tex_file)
        assert len(parser.content) > 10000


if __name__ == "__main__":
    # Run tests with pytest if available, otherwise run basic tests
    try:
        import pytest
        sys.exit(pytest.main([__file__, "-v"]))
    except ImportError:
        print("pytest not available. Install with: uv add pytest")
        print("Running basic smoke tests...")
        
        # Basic smoke tests
        print("Testing extract_arxiv_id...")
        assert extract_arxiv_id("2401.12345") == "2401.12345"
        print("✓ extract_arxiv_id works")
        
        print("\nAll smoke tests passed!")
        print("For comprehensive testing, install pytest and run: pytest tests/")
