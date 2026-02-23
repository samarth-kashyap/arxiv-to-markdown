"""Command-line interface for arxiv-to-markdown."""

import shutil
import sys
import tempfile
from pathlib import Path

import click

from .downloader import (
    ArxivDownloadError,
    download_source,
    extract_arxiv_id,
    find_bibliography_files,
    find_main_tex,
)
from .parser import LaTeXParser, LaTeXParserError
from .bibtex_handler import BibliographyHandler
from .converter import LaTeXConversionError, LaTeXConverter
from .postprocessor import MarkdownPostProcessor


@click.command()
@click.argument('arxiv_input')
@click.option(
    '--output-dir', '-o',
    type=click.Path(path_type=Path),
    default=None,
    help='Output directory (default: ./<arxiv_id>)'
)
@click.option(
    '--keep-source', '-k',
    is_flag=True,
    help='Keep downloaded source files'
)
@click.option(
    '--verbose', '-v',
    is_flag=True,
    help='Verbose output'
)
@click.version_option(version='0.1.0')
def main(arxiv_input, output_dir, keep_source, verbose):
    """Convert an arXiv paper to markdown.
    
    ARXIV_INPUT can be:
    - arXiv ID: 2401.12345
    - URL: https://arxiv.org/abs/2401.12345
    - arXiv notation: arXiv:2401.12345
    """
    try:
        # Step 1: Extract arXiv ID
        try:
            arxiv_id = extract_arxiv_id(arxiv_input)
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        
        if verbose:
            click.echo(f"Processing arXiv ID: {arxiv_id}")
        
        # Step 2: Setup output directory
        if output_dir is None:
            output_dir = Path.cwd() / arxiv_id
        
        # Check if output directory already exists
        if output_dir.exists() and any(output_dir.iterdir()):
            if not click.confirm(
                f"Directory {output_dir} already exists and is not empty. Overwrite?",
                default=False
            ):
                click.echo("Aborted.")
                sys.exit(0)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Step 3: Download source
        if verbose:
            click.echo("Downloading source files...")
        
        try:
            source_dir = download_source(arxiv_id, output_dir)
        except ArxivDownloadError as e:
            click.echo(f"Error downloading paper: {e}", err=True)
            sys.exit(1)
        except FileNotFoundError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        
        # Step 4: Find main files
        try:
            main_tex = find_main_tex(source_dir)
        except FileNotFoundError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        
        bbl_path, bib_path = find_bibliography_files(source_dir)
        
        if verbose:
            click.echo(f"Main tex file: {main_tex.name}")
            if bbl_path:
                click.echo(f"Bibliography: {bbl_path.name}")
            elif bib_path:
                click.echo(f"Bibliography: {bib_path.name}")
        
        # Step 5: Parse LaTeX structure
        if verbose:
            click.echo("Parsing LaTeX structure...")
        
        try:
            parser = LaTeXParser(main_tex, source_dir=source_dir)
        except LaTeXParserError as e:
            click.echo(f"Error parsing LaTeX: {e}", err=True)
            sys.exit(1)
        
        main_content, appendix_content, embedded_bib = parser.split_document()
        
        # Step 6: Handle bibliography
        if verbose:
            click.echo("Processing bibliography...")
        
        # If there's embedded bibliography content, create a temp bbl file
        temp_bbl_path = None
        if embedded_bib and not bbl_path:
            try:
                with tempfile.NamedTemporaryFile(
                    mode='w', suffix='.bbl', delete=False
                ) as tmp:
                    tmp.write(embedded_bib)
                    temp_bbl_path = Path(tmp.name)
                    bbl_path = temp_bbl_path
            except IOError as e:
                click.echo(f"Warning: Could not process embedded bibliography: {e}", err=True)
        
        bib_handler = BibliographyHandler(bbl_path, bib_path)
        
        # Try to enrich bibliography with arxiv lookups for any missing citations
        citations = parser.extract_citations()
        if verbose and citations:
            click.echo(f"Found {len(citations)} citations")
        
        for cite_key in citations:
            if cite_key not in bib_handler.citations:
                if verbose:
                    click.echo(f"  Looking up citation: {cite_key}")
                bib_handler.resolve_citation(cite_key)
        
        # Step 7: Convert to markdown
        if verbose:
            click.echo("Converting to markdown...")
        
        converter = LaTeXConverter(bib_handler, parser.labels)
        
        try:
            main_md = converter.convert(main_content)
        except LaTeXConversionError as e:
            click.echo(f"Error converting main content: {e}", err=True)
            sys.exit(1)
        
        appendix_md = None
        if appendix_content:
            try:
                appendix_md = converter.convert(appendix_content)
            except LaTeXConversionError as e:
                click.echo(f"Warning: Error converting appendix: {e}", err=True)
                click.echo("Continuing without appendix...")
        
        # Step 8: Post-process
        if verbose:
            click.echo("Post-processing...")
        
        postprocessor = MarkdownPostProcessor()
        
        bibliography = bib_handler.generate_bibliography()
        main_md = postprocessor.process(main_md, bibliography)
        
        if appendix_md:
            appendix_md = postprocessor.process(appendix_md)
        
        # Step 9: Split appendix if it wasn't already separate
        main_final, appendix_final = postprocessor.split_appendix(main_md)
        if appendix_final:
            main_md = main_final
            appendix_md = appendix_final
        
        # Step 10: Write output files
        main_file = output_dir / f"{arxiv_id}_main.md"
        try:
            main_file.write_text(main_md, encoding='utf-8')
            click.echo(f"Written: {main_file}")
        except IOError as e:
            click.echo(f"Error writing main file: {e}", err=True)
            sys.exit(1)
        
        if appendix_md:
            appendix_file = output_dir / f"{arxiv_id}_appendix.md"
            try:
                appendix_file.write_text(appendix_md, encoding='utf-8')
                click.echo(f"Written: {appendix_file}")
            except IOError as e:
                click.echo(f"Warning: Error writing appendix file: {e}", err=True)
        
        # Cleanup if requested
        if not keep_source:
            if source_dir.exists():
                shutil.rmtree(source_dir, ignore_errors=True)
        
        # Cleanup temp bbl file if created
        if temp_bbl_path and temp_bbl_path.exists():
            temp_bbl_path.unlink(missing_ok=True)
        
        click.echo(f"\nConversion complete! Files saved to: {output_dir}")
        
    except KeyboardInterrupt:
        click.echo("\nOperation cancelled by user.", err=True)
        sys.exit(130)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
