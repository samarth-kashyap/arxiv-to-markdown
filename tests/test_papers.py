#!/usr/bin/env python3
"""Comprehensive test script for arxiv-to-markdown converter.

This script tests the converter with a variety of arXiv papers to identify
edge cases and ensure robustness.
"""

import sys
import tempfile
import traceback
from pathlib import Path
from typing import List, Tuple

# Add the package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from arxiv_to_md.downloader import (
    download_source,
    extract_arxiv_id,
    find_bibliography_files,
    find_main_tex,
    ArxivDownloadError,
)
from arxiv_to_md.parser import LaTeXParser, LaTeXParserError
from arxiv_to_md.bibtex_handler import BibliographyHandler
from arxiv_to_md.converter import LaTeXConverter, LaTeXConversionError
from arxiv_to_md.postprocessor import MarkdownPostProcessor


# Test papers covering different scenarios
TEST_PAPERS = [
    # Format: (arxiv_id, description, expected_to_work)
    ("2405.02700", "CVPR paper with subdirs (original failing case)", True),
    ("1706.03762", "Attention is All You Need (classic)", True),
    ("2301.07092", "Recent paper", True),
    ("2009.00031", "GPT-3 paper", True),
    ("2210.02410", "Paper with LaTeX syntax issues", False),  # Known to fail
    ("1810.04805", "BERT paper with title issues", False),  # Known to fail
    ("2402.17287", "Another recent paper", True),
    ("2106.04566", "Paper with figures", True),
    ("2104.08718", "CLIPScore paper", True),
    ("2011.10650", "Very Deep VAE paper", True),
    # Additional diverse papers
    ("2212.09748", "DiT paper (Scalable Diffusion Models)", True),
    ("2303.08774", "GPT-4 Technical Report", True),
    ("2110.08207", "Vision Transformer (ViT)", True),
    ("2009.00030", "Improved guarantees and a multiple-descent curve for Column Subset Selection", True),
    ("2109.03917", "Swin Transformer", False),  # Complex LaTeX syntax issues
    ("2204.06125", "PaLM: Scaling Language Modeling with Pathways", True),  # Now works with preprocessing
    ("2010.11929", "An Image is Worth 16x16 Words (ViT)", True),
    ("1909.05858", "ALBERT: A Lite BERT", True),
]


def test_paper(arxiv_id: str, description: str, expected_to_work: bool) -> Tuple[bool, str]:
    """Test a single paper.
    
    Returns:
        Tuple of (success, message)
    """
    print(f"\n{'='*60}")
    print(f"Testing: {arxiv_id} - {description}")
    print(f"Expected to work: {expected_to_work}")
    print('='*60)
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            
            # Step 1: Download
            print(f"  [1/6] Downloading source...")
            try:
                source_dir = download_source(arxiv_id, output_dir, max_retries=2)
            except ArxivDownloadError as e:
                return False, f"Download failed: {e}"
            
            # Step 2: Find main tex
            print(f"  [2/6] Finding main tex file...")
            try:
                main_tex = find_main_tex(source_dir)
                print(f"    Found: {main_tex.relative_to(source_dir)}")
            except FileNotFoundError as e:
                return False, f"No main tex found: {e}"
            
            # Step 3: Parse LaTeX
            print(f"  [3/6] Parsing LaTeX structure...")
            try:
                parser = LaTeXParser(main_tex, source_dir=source_dir)
                main_content, appendix_content, embedded_bib = parser.split_document()
                citations = parser.extract_citations()
                print(f"    Found {len(citations)} citations")
            except LaTeXParserError as e:
                return False, f"Parse error: {e}"
            
            # Step 4: Handle bibliography
            print(f"  [4/6] Processing bibliography...")
            bbl_path, bib_path = find_bibliography_files(source_dir)
            bib_handler = BibliographyHandler(bbl_path, bib_path)
            
            # Resolve citations
            for cite_key in citations:
                if cite_key not in bib_handler.citations:
                    bib_handler.resolve_citation(cite_key)
            
            # Step 5: Convert
            print(f"  [5/6] Converting to markdown...")
            converter = LaTeXConverter(bib_handler)
            
            try:
                main_md = converter.convert(main_content)
                word_count = len(main_md.split())
                print(f"    Generated {word_count} words")
                
                if appendix_content:
                    appendix_md = converter.convert(appendix_content)
                    print(f"    Generated appendix ({len(appendix_md.split())} words)")
            except LaTeXConversionError as e:
                return False, f"Conversion failed: {e}"
            
            # Step 6: Post-process
            print(f"  [6/6] Post-processing...")
            postprocessor = MarkdownPostProcessor()
            bibliography = bib_handler.generate_bibliography()
            main_md = postprocessor.process(main_md, bibliography)
            
            # Verify output quality
            issues = []
            if len(main_md) < 1000:
                issues.append(f"Output seems too short ({len(main_md)} chars)")
            if main_md.count('#') < 3:
                issues.append("Too few headers")
            
            if issues:
                return False, f"Quality issues: {'; '.join(issues)}"
            
            return True, f"Success! {word_count} words, {len(citations)} citations"
            
    except Exception as e:
        return False, f"Unexpected error: {type(e).__name__}: {e}"


def run_tests():
    """Run all tests and generate report."""
    print("="*60)
    print("ARXIV-TO-MARKDOWN COMPREHENSIVE TEST SUITE")
    print("="*60)
    
    results = []
    passed = 0
    failed = 0
    unexpected = 0
    
    for arxiv_id, description, expected_to_work in TEST_PAPERS:
        success, message = test_paper(arxiv_id, description, expected_to_work)
        results.append((arxiv_id, description, expected_to_work, success, message))
        
        if success == expected_to_work:
            if success:
                passed += 1
                status = "✓ PASS"
            else:
                passed += 1  # Expected failure is still a pass
                status = "✓ PASS (expected failure)"
        else:
            if success and not expected_to_work:
                unexpected += 1
                status = "✓ UNEXPECTED SUCCESS"
            else:
                failed += 1
                status = "✗ FAIL"
        
        print(f"\n  Status: {status}")
        print(f"  Message: {message}")
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Total tests: {len(TEST_PAPERS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Unexpected successes: {unexpected}")
    
    print("\nDetailed Results:")
    print("-"*60)
    for arxiv_id, description, expected, success, message in results:
        status = "✓" if success == expected else "✗"
        print(f"{status} {arxiv_id}: {message}")
    
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
