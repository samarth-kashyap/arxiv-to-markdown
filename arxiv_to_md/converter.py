"""Module for converting LaTeX to Markdown using Pandoc."""

import re
import tempfile
from pathlib import Path
from typing import Optional

import pypandoc

from .bibtex_handler import BibliographyHandler


class LaTeXConversionError(Exception):
    """Custom exception for LaTeX conversion failures."""
    pass


class LaTeXConverter:
    """Convert LaTeX to Markdown using Pandoc."""
    
    def __init__(self, bib_handler: Optional[BibliographyHandler] = None):
        self.bib_handler = bib_handler
    
    def convert(
        self,
        tex_content: str,
        filter_path: Optional[Path] = None
    ) -> str:
        """Convert LaTeX content to Markdown.
        
        Args:
            tex_content: Raw LaTeX content
            filter_path: Path to custom Pandoc Lua filter
            
        Returns:
            Markdown content
            
        Raises:
            LaTeXConversionError: If conversion fails
        """
        if not tex_content or not tex_content.strip():
            raise LaTeXConversionError("Empty LaTeX content provided")
        
        # Pre-process: remove LaTeX commands that don't convert well
        tex_content = self._preprocess_commands(tex_content)
        
        # Pre-process references (not citations - those will be handled post-pandoc)
        tex_content = self._preprocess_references(tex_content)
        
        # Write to temp file for pandoc
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.tex', delete=False
        ) as tmp:
            tmp.write(tex_content)
            tmp_path = tmp.name
        
        try:
            # Build pandoc arguments
            extra_args = [
                '--from=latex+raw_tex',
                '--to=markdown',
                '--mathjax',
                '--wrap=none',
                '--syntax-highlighting=none',
            ]
            
            if filter_path and filter_path.exists():
                extra_args.extend(['--lua-filter', str(filter_path)])
            
            # Run pandoc
            try:
                output = pypandoc.convert_file(
                    tmp_path,
                    'md',
                    format='latex',
                    extra_args=extra_args
                )
            except RuntimeError as e:
                raise LaTeXConversionError(f"Pandoc conversion failed: {e}")
            
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        
        # Post-process citations in markdown
        output = self._postprocess_citations(output)
        
        return output
    
    def _preprocess_commands(self, content: str) -> str:
        """Remove LaTeX commands that don't convert well to markdown.
        
        Only removes commands outside of math environments.
        """
        # Remove \maketitle
        content = re.sub(r'\\maketitle\b', '', content)
        
        # Remove \documentclass, \usepackage, etc. (preamble commands)
        content = re.sub(r'\\documentclass(?:\[[^\]]*\])?\{[^}]*\}', '', content)
        content = re.sub(r'\\usepackage(?:\[[^\]]*\])?\{[^}]*\}', '', content)
        
        # Note: Don't remove \author as it may span multiple lines with nested braces
        # Pandoc can handle it fine. Only remove simple commands.
        content = re.sub(r'\\title\{[^}]*\}', '', content)
        content = re.sub(r'\\date\{[^}]*\}', '', content)
        
        # Remove author information commands
        content = re.sub(r'\\email\{[^}]*\}', '', content)
        content = re.sub(r'\\affiliation\{[^}]*\}', '', content)
        content = re.sub(r'\\institute\{[^}]*\}', '', content)
        content = re.sub(r'\\address\{[^}]*\}', '', content)
        
        # Remove problematic environments that Pandoc can't handle
        # bibunit environment
        content = re.sub(r'\\begin\{bibunit\}', '', content)
        content = re.sub(r'\\end\{bibunit\}', '', content)
        
        # Remove \parhead and similar custom commands that might be redefined
        content = re.sub(r'\\parhead\b', '', content)
        
        # Remove \DeclarePairedDelimiter and similar command definitions
        # These use #1, #2 etc as parameter placeholders which Pandoc can't handle
        # Handle multi-line definitions
        content = re.sub(r'\\DeclarePairedDelimiter\{[^}]+\}\{[^}]+\}\{[^}]+\}', '', content, flags=re.DOTALL)
        content = re.sub(r'\\DeclarePairedDelimiterX[^\n]*\n[^}]+\}', '', content, flags=re.DOTALL)
        content = re.sub(r'\\DeclareRobustCommand\{[^}]+\}\[[^\]]*\]\{[^}]+\}', '', content, flags=re.DOTALL)
        
        # Remove citation name formatting commands that appear in text
        content = re.sub(r'\\citenamefont\{([^}]+)\}', r'\1', content)
        content = re.sub(r'\\bibfnamefont\{([^}]+)\}', r'\1', content)
        content = re.sub(r'\\bibnamefont\{([^}]+)\}', r'\1', content)
        
        return content
    
    def _postprocess_citations(self, content: str) -> str:
        """Post-process citation keys in markdown output.
        
        Converts Pandoc citation format [@key] to markdown links.
        """
        if not self.bib_handler:
            return content
        
        # Handle multiple citations: [@key1; @key2; @key3]
        multi_cite_pattern = r'\[(@[a-zA-Z0-9_-]+(?:;\s*@[a-zA-Z0-9_-]+)*)\]'
        
        def replace_multi_cite(match):
            cites_str = match.group(1)
            # Extract individual keys
            keys = re.findall(r'@([a-zA-Z0-9_-]+)', cites_str)
            formatted = []
            for key in keys:
                if key in self.bib_handler.citations:
                    formatted.append(self.bib_handler.format_citation_markdown(key))
                else:
                    formatted.append(f'[@{key}]')
            return '; '.join(formatted) if formatted else match.group(0)
        
        content = re.sub(multi_cite_pattern, replace_multi_cite, content)
        
        # Handle single citations: [@key]
        single_cite_pattern = r'\[@([a-zA-Z0-9_-]+)\]'
        
        def replace_single_cite(match):
            key = match.group(1)
            if key in self.bib_handler.citations:
                return self.bib_handler.format_citation_markdown(key)
            return match.group(0)
        
        content = re.sub(single_cite_pattern, replace_single_cite, content)
        
        return content
    
    def _preprocess_references(self, content: str) -> str:
        r"""Pre-process reference commands (\ref, \eqref, etc.).
        
        Converts references like "Equation \ref{eq:1}" to just "Equation".
        """
        # Match patterns like "Equation \ref{...}", "Fig. \ref{...}", etc.
        ref_context_pattern = r'(Equation|Eq\.?|Fig\.?|Figure|Table|Tab\.?|Section|Sec\.)\s*\\(?:eq)?ref\{[^}]+\}'
        
        def replace_ref_context(match):
            # Keep just the type (Equation, Figure, etc.)
            ref_type = match.group(1)
            # Normalize abbreviations
            if ref_type.lower() in ['eq.', 'eq']:
                return 'Equation'
            elif ref_type.lower() in ['fig.', 'fig']:
                return 'Figure'
            elif ref_type.lower() in ['tab.', 'tab']:
                return 'Table'
            elif ref_type.lower() in ['sec.', 'sec']:
                return 'Section'
            return ref_type
        
        content = re.sub(ref_context_pattern, replace_ref_context, content, flags=re.IGNORECASE)
        
        # Remove any remaining bare \ref{...} or \eqref{...}
        content = re.sub(r'\\(?:eq)?ref\{[^}]+\}', '', content)
        
        # Remove \label commands
        content = re.sub(r'\\label\{[^}]+\}', '', content)
        
        return content
