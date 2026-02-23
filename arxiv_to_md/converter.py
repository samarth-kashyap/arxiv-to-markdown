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


def _remove_nested_command(content: str, cmd: str) -> str:
    """Remove LaTeX command with potentially nested braces.
    
    Handles commands that may span multiple lines and have nested braces.
    Also handles optional arguments like \\command[opt]{...}
    
    Args:
        content: LaTeX content
        cmd: Command name without backslash (e.g., 'address', 'thanks')
        
    Returns:
        Content with command removed
    """
    pattern = rf'\\{cmd}(?:\[[^\]]*\])?\{{'
    result = []
    i = 0
    
    while i < len(content):
        match = re.search(pattern, content[i:])
        if not match:
            result.append(content[i:])
            break
            
        result.append(content[i:i + match.start()])
        
        start = i + match.end()
        brace_count = 1
        j = start
        
        while j < len(content) and brace_count > 0:
            if content[j] == '{':
                brace_count += 1
            elif content[j] == '}':
                brace_count -= 1
            j += 1
        
        i = j
    
    return ''.join(result)


class LaTeXConverter:
    """Convert LaTeX to Markdown using Pandoc."""
    
    def __init__(self, bib_handler: Optional[BibliographyHandler] = None):
        self.bib_handler = bib_handler
    
    def convert(self, tex_content: str, filter_path: Optional[Path] = None) -> str:
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
                '--from=latex+raw_tex+latex_macros',
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
        Note: \newcommand, \renewcommand, etc. are now preserved and expanded
        by pandoc's +latex_macros extension.
        """
        # Document structure commands
        content = re.sub(r'\\maketitle\b', '', content)
        content = re.sub(r'\\documentclass(?:\[[^\]]*\])?\{[^}]*\}', '', content)
        content = re.sub(r'\\tableofcontents\b', '', content)

        # Package and preamble commands (simple, single-line)
        content = re.sub(r'\\usepackage(?:\[[^\]]*\])?\{[^}]*\}', '', content)
        content = re.sub(r'\\title\{[^}]*\}', '', content)
        content = re.sub(r'\\date\{[^}]*\}', '', content)

        # Author information commands (handle multi-line with nested braces)
        author_cmds = ['email', 'affiliation', 'institute', 'address', 'thanks', 'author']
        for cmd in author_cmds:
            content = _remove_nested_command(content, cmd)

        # Frontmatter commands (elsarticle, revtex, etc.)
        content = re.sub(r'\\begin\{frontmatter\}', '', content)
        content = re.sub(r'\\end\{frontmatter\}', '', content)
        content = re.sub(r'\\begin\{abstract\}', '', content)
        content = re.sub(r'\\end\{abstract\}', '', content)
        content = re.sub(r'\\begin\{keyword\}', '', content)
        content = re.sub(r'\\end\{keyword\}', '', content)
        content = re.sub(r'\\journal\{[^}]*\}', '', content)
        content = re.sub(r'\\appendix', '', content)
        
        # Additional elsarticle-specific cleanup (with optional arguments)
        content = re.sub(r'\\affiliation(?:\[[^\]]*\])?\{[^}]*\}', '', content)
        content = re.sub(r'\\author(?:\[[^\]]*\])?\{[^}]*\}', '', content)

        # Metadata and classification commands
        meta_cmds_simple = [
            (r'\\makeatletter\b', ''),
            (r'\\makeatother\b', ''),
            (r'\\numberwithin\{[^}]+\}\{[^}]+\}', ''),
            (r'\\hyphenation\{[^}]+\}', ''),
            (r'\\subjclass(?:\[[^\]]*\])?\{[^}]*\}', ''),
            (r'\\setcounter\{[^}]+\}\{[^}]+\}', ''),
            (r'\\addtoreset\{[^}]+\}\{[^}]+\}', ''),
            (r'\\addtoreset\w*', ''),
            (r'\\@addtoreset\{[^}]+\}\{[^}]+\}', ''),
        ]
        for pattern, repl in meta_cmds_simple:
            content = re.sub(pattern, repl, content)

        # Theorem and environment definitions (handle double braces like \newtheorem{name}{{Definition}})
        content = re.sub(r'\\newtheorem\{[^}]+\}(?:\[[^\]]*\])?(?:\{\{?[^}]*\}?\})?(?:\[[^\]]*\])?', '', content)
        content = re.sub(r'\\theoremstyle\{[^}]+\}', '', content)

        # Remove conditional compilation commands (\ifdefined\NAME, not \ifdefined{NAME})
        content = re.sub(r'\\ifdefined\\[a-zA-Z]+', '', content)
        content = re.sub(r'\\else\b', '', content)
        content = re.sub(r'\\fi\b', '', content)

        # Remove IEEE-specific commands
        content = re.sub(r'\\IEEEPARstart\{[^}]*\}\{[^}]*\}', '', content)
        content = re.sub(r'\\IEEEmembership\{[^}]*\}', '', content)
        content = re.sub(r'\\IEEEproof', '', content)
        content = re.sub(r'\\IEEEkeywords', '', content)
        content = re.sub(r'\\end\{IEEEkeywords\}', '', content)
        content = re.sub(r'\\begin\{keywords\}', '', content)
        content = re.sub(r'\\end\{keywords\}', '', content)
        content = re.sub(r'\\thanks\{[^}]*\}', '', content)

        # Handle ICML (and similar conference) specific commands
        # Remove icmltitle but keep content (it's metadata, not body)
        content = _remove_nested_command(content, 'icmltitle')
        content = _remove_nested_command(content, 'icmltitlerunning')
        content = _remove_nested_command(content, 'icmlauthor')
        content = _remove_nested_command(content, 'icmlaffiliation')
        content = _remove_nested_command(content, 'icmlcorrespondingauthor')
        content = re.sub(r'\\icmlkeywords\{[^}]*\}', '', content)
        content = re.sub(r'\\icmlsetsymbol\{[^}]*\}\{[^}]*\}', '', content)
        content = re.sub(r'\\icmlEqualContribution', '', content)
        content = re.sub(r'\\icmlIntern', '', content)
        content = re.sub(r'\\icmladdress\{[^}]*\}', '', content)
        content = re.sub(r'\\printAffiliationsAndNotice\{[^}]*\}', '', content)
        
        # ICML environments
        content = re.sub(r'\\begin\{icmlauthorlist\}', '', content)
        content = re.sub(r'\\end\{icmlauthorlist\}', '', content)
        
        # Title bars and formatting
        content = re.sub(r'\\toptitlebar', '', content)
        content = re.sub(r'\\bottomtitlebar', '', content)
        
        # Remove twocolumn wrapper but keep content: \twocolumn[...]
        # This requires special handling because the content can span multiple lines
        # and contain nested brackets
        content = self._remove_twocolumn_wrapper(content)

        # Page and formatting commands
        content = re.sub(r'\\newpage\b', '', content)
        content = re.sub(r'\\pagebreak\b', '', content)
        content = re.sub(r'\\nopagebreak\b', '', content)
        content = re.sub(r'\\clearpage\b', '', content)
        
        # Vertical spacing commands
        content = re.sub(r'\\vskip\s+[\d.]+\w*', '', content)
        content = re.sub(r'\\vspace\{[^}]*\}', '', content)
        content = re.sub(r'\\hspace\{[^}]*\}', '', content)
        content = re.sub(r'\\smallskip\b', '', content)
        content = re.sub(r'\\medskip\b', '', content)
        content = re.sub(r'\\bigskip\b', '', content)

        # Problematic environments
        content = re.sub(r'\\begin\{bibunit\}', '', content)
        content = re.sub(r'\\end\{bibunit\}', '', content)

        # Custom command definitions that confuse Pandoc
        cmd_defs = [
            r'\\DeclarePairedDelimiter\{[^}]+\}\{[^}]+\}\{[^}]+\}',
            r'\\DeclarePairedDelimiterX[^\n]*\n[^}]+\}',
            r'\\DeclareRobustCommand\{[^}]+\}\[[^\]]*\]\{[^}]+\}',
            r'\\parhead\b',
            r'\\soulregister[^\n]*',
        ]
        for pattern in cmd_defs:
            content = re.sub(pattern, '', content, flags=re.DOTALL)

        # Citation formatting commands (extract content only)
        cite_formats = [
            (r'\\citenamefont\{([^}]+)\}', r'\1'),
            (r'\\bibfnamefont\{([^}]+)\}', r'\1'),
            (r'\\bibnamefont\{([^}]+)\}', r'\1'),
        ]
        for pattern, repl in cite_formats:
            content = re.sub(pattern, repl, content)

        # Graphics and color commands (nested braces)
        graphics_cmds = [
            'usetikzlibrary', 'tikzset', 'pgfplotsset',
            'definecolor', 'color', 'colorlet',
            'keyword', 'keywords', 'pacs', 'pagecolor',
            'textcolor', 'colorbox', 'fcolorbox'
        ]
        for cmd in graphics_cmds:
            content = _remove_nested_command(content, cmd)
        
        # Note: Color macros (\red, \blue, etc.) are now handled by pandoc's
        # +latex_macros extension which expands them properly. We don't remove
        # them here to avoid breaking \newcommand definitions like:
        #   \newcommand{\red}[1]{\textcolor{red}{#1}}

        # Remove raw_tex attributes from pandoc output
        content = re.sub(r'`[^`]*`\{=latex\}', '', content)

        return content
    
    def _remove_newcommand_definitions(self, content: str, cmd_type: str) -> str:
        """Remove \newcommand, \renewcommand, etc. definitions.
        
        These have a special structure: \\cmd{\\name}[nargs]{definition}
        where nargs is optional and there can be multiple definition blocks.
        """
        # Pattern matches: \cmd{\name} or \cmd{\name}[nargs]
        pattern = rf'\\{re.escape(cmd_type)}(?:\*)?\{{[^}}]+\}}(?:\[[^\]]*\])?'
        
        result = []
        i = 0
        
        while i < len(content):
            match = re.search(pattern, content[i:])
            if not match:
                result.append(content[i:])
                break
            
            # Append content before command
            result.append(content[i:i + match.start()])
            
            # Find all the definition blocks (braced content)
            start = i + match.end()
            brace_count = 0
            j = start
            in_brace = False
            
            while j < len(content):
                if content[j] == '{':
                    brace_count += 1
                    in_brace = True
                elif content[j] == '}':
                    brace_count -= 1
                    if brace_count == 0 and in_brace:
                        # Finished one definition block
                        j += 1
                        # Check if there's another brace immediately after
                        if j < len(content) and content[j] == '{':
                            in_brace = False
                            continue
                        else:
                            break
                j += 1
            
            # Move past the command and its definition
            i = j
        
        return ''.join(result)
    
    def _remove_twocolumn_wrapper(self, content: str) -> str:
        """Remove \twocolumn[...] wrapper but keep the content inside.
        
        ICML and similar templates use \twocolumn[...] to place the title,
        authors, and abstract in a single column at the top. We want to
        remove the wrapper but preserve the content.
        """
        # Pattern to match \twocolumn[
        pattern = r'\\twocolumn\['
        
        result = []
        i = 0
        
        while i < len(content):
            match = re.search(pattern, content[i:])
            if not match:
                result.append(content[i:])
                break
            
            # Append content before the twocolumn
            result.append(content[i:i + match.start()])
            
            # Find the matching closing bracket
            start = i + match.end()
            bracket_count = 1
            j = start
            
            while j < len(content) and bracket_count > 0:
                if content[j] == '[':
                    bracket_count += 1
                elif content[j] == ']':
                    bracket_count -= 1
                j += 1
            
            # Append the content inside the brackets (j-1 because j is past the closing bracket)
            if bracket_count == 0:
                inner_content = content[start:j-1]
                result.append(inner_content)
            else:
                # No matching bracket found, keep everything
                result.append(content[start:])
                break
            
            i = j
        
        return ''.join(result)
    
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
