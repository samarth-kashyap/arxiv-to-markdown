"""Module for converting LaTeX to Markdown using Pandoc."""

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import pypandoc

from .bibtex_handler import BibliographyHandler


class LaTeXConversionError(Exception):
    """Custom exception for LaTeX conversion failures."""
    pass


@dataclass
class CommandPattern:
    """Definition of a LaTeX command pattern to remove/process.
    
    Attributes:
        name: Command name (without backslash)
        pattern: Regex pattern to match the command
        replacement: Replacement string (default: empty string)
        handler: Optional custom handler function for complex cases
        flags: Regex flags
    """
    name: str
    pattern: str
    replacement: str = ''
    handler: Optional[Callable[[str, 'CommandPattern'], str]] = None
    flags: int = 0


class LaTeXCommandProcessor:
    """Process LaTeX commands using declarative patterns.
    
    This class provides a clean, extensible way to define and apply
    LaTeX command transformations.
    """
    
    # Standard command categories organized by behavior
    SIMPLE_COMMANDS = [
        # Document structure
        'maketitle', 'tableofcontents', 'listoffigures', 'listoftables',
        # Page breaks
        'newpage', 'pagebreak', 'nopagebreak', 'clearpage',
        # Vertical spacing
        'smallskip', 'medskip', 'bigskip',
        # Formatting
        'centering', 'raggedright', 'raggedleft',
    ]
    
    ENVIRONMENTS_TO_REMOVE = [
        'frontmatter', 'abstract', 'keyword', 'keywords',
        'icmlauthorlist', 'IEEEkeywords',
    ]
    
    COMMANDS_WITH_SIMPLE_ARGS = [
        # Document structure
        (r'documentclass(?:\[[^\]]*\])?\{[^}]*\}', ''),
        (r'title\{[^}]*\}', ''),
        (r'date\{[^}]*\}', ''),
        (r'journal\{[^}]*\}', ''),
        # Packages
        (r'usepackage(?:\[[^\]]*\])?\{[^}]*\}', ''),
        # Metadata
        (r'subjclass(?:\[[^\]]*\])?\{[^}]*\}', ''),
        (r'hyphenation\{[^}]*\}', ''),
        (r'setcounter\{[^}]+\}\{[^}]+\}', ''),
        # Theorem setup
        (r'theoremstyle\{[^}]*\}', ''),
        # Formatting - keep the content (last argument)
        (r'textcolor\{[^}]+\}\{([^}]+)\}', r'\1'),
        (r'colorbox\{[^}]+\}\{([^}]+)\}', r'\1'),
        (r'fcolorbox\{[^}]+\}\{[^}]+\}\{([^}]+)\}', r'\1'),
    ]
    
    COUNTER_COMMANDS = [
        (r'addtoreset\{[^}]+\}\{[^}]+\}', ''),
        (r'addtoreset\w*', ''),
        (r'@addtoreset\{[^}]+\}\{[^}]+\}', ''),
        (r'numberwithin\{[^}]+\}\{[^}]+\}', ''),
    ]
    
    CONDITIONAL_COMMANDS = [
        (r'ifdefined\\[a-zA-Z]+', ''),
        (r'else\b', ''),
        (r'fi\b', ''),
        (r'makeatletter\b', ''),
        (r'makeatother\b', ''),
    ]
    
    ICML_COMMANDS = [
        (r'icmlkeywords\{[^}]*\}', ''),
        (r'icmlsetsymbol\{[^}]*\}\{[^}]*\}', ''),
        (r'icmlEqualContribution', ''),
        (r'icmlIntern', ''),
        (r'icmladdress\{[^}]*\}', ''),
        (r'printAffiliationsAndNotice\{[^}]*\}', ''),
        (r'toptitlebar', ''),
        (r'bottomtitlebar', ''),
    ]
    
    IEEE_COMMANDS = [
        (r'IEEEPARstart\{[^}]*\}\{[^}]*\}', ''),
        (r'IEEEmembership\{[^}]*\}', ''),
        (r'IEEEproof', ''),
        (r'IEEEkeywords', ''),
    ]
    
    SPACING_COMMANDS = [
        (r'vskip\s+[\d.]+\w*', ''),
        (r'vspace\{[^}]*\}', ''),
        (r'hspace\{[^}]*\}', ''),
    ]
    
    CITATION_FONT_COMMANDS = [
        (r'citenamefont\{([^}]+)\}', r'\1'),
        (r'bibfnamefont\{([^}]+)\}', r'\1'),
        (r'bibnamefont\{([^}]+)\}', r'\1'),
    ]
    
    PROBLEMATIC_DEFS = [
        r'DeclarePairedDelimiter\{[^}]+\}\{[^}]+\}\{[^}]+\}',
        r'DeclarePairedDelimiterX[^\n]*\n[^}]+\}',
        r'DeclareRobustCommand\{[^}]+\}\[[^\]]*\]\{[^}]+\}',
        r'parhead\b',
        r'soulregister[^\n]*',
    ]
    
    def __init__(self):
        self.patterns: List[CommandPattern] = []
        self._build_patterns()
    
    def _build_patterns(self):
        """Build all command patterns."""
        # Simple commands (just the command name)
        for cmd in self.SIMPLE_COMMANDS:
            self.patterns.append(CommandPattern(
                name=cmd,
                pattern=rf'\\{cmd}\b',
                replacement=''
            ))
        
        # Environments to remove entirely
        for env in self.ENVIRONMENTS_TO_REMOVE:
            self.patterns.append(CommandPattern(
                name=f'begin/end_{env}',
                pattern=rf'\\(?:begin|end)\{{{env}\}}',
                replacement=''
            ))
        
        # Commands with simple arguments
        for pattern, replacement in self.COMMANDS_WITH_SIMPLE_ARGS:
            cmd_name = pattern.split('\\')[1].split('{')[0].split('[')[0]
            self.patterns.append(CommandPattern(
                name=cmd_name,
                pattern=rf'\\{pattern}',
                replacement=replacement
            ))
        
        # Counter commands
        for pattern, replacement in self.COUNTER_COMMANDS:
            self.patterns.append(CommandPattern(
                name='counter_cmd',
                pattern=rf'\\{pattern}',
                replacement=replacement
            ))
        
        # Conditional commands
        for pattern, replacement in self.CONDITIONAL_COMMANDS:
            self.patterns.append(CommandPattern(
                name='conditional',
                pattern=rf'\\{pattern}',
                replacement=replacement
            ))
        
        # Conference-specific commands
        for pattern, replacement in self.ICML_COMMANDS:
            cmd_name = pattern.split('{')[0].split('[')[0].replace('\\', '')
            self.patterns.append(CommandPattern(
                name=f'icml_{cmd_name}',
                pattern=rf'\\{pattern}',
                replacement=replacement
            ))
        
        for pattern, replacement in self.IEEE_COMMANDS:
            cmd_name = pattern.split('{')[0].replace('\\', '')
            self.patterns.append(CommandPattern(
                name=f'ieee_{cmd_name}',
                pattern=rf'\\{pattern}',
                replacement=replacement
            ))
        
        # Spacing commands
        for pattern, replacement in self.SPACING_COMMANDS:
            self.patterns.append(CommandPattern(
                name='spacing',
                pattern=rf'\\{pattern}',
                replacement=replacement
            ))
        
        # Citation font commands (keep content)
        for pattern, replacement in self.CITATION_FONT_COMMANDS:
            cmd_name = pattern.split('{')[0].replace('\\', '')
            self.patterns.append(CommandPattern(
                name=cmd_name,
                pattern=rf'\\{pattern}',
                replacement=replacement
            ))
        
        # Problematic definitions
        for pattern in self.PROBLEMATIC_DEFS:
            cmd_name = pattern.split('{')[0].split('\\')[1].split('[')[0]
            self.patterns.append(CommandPattern(
                name=f'def_{cmd_name}',
                pattern=rf'\\{pattern}',
                replacement='',
                flags=re.DOTALL
            ))
        
        # Special handlers for complex cases
        self.patterns.append(CommandPattern(
            name='newtheorem',
            pattern=rf'\\newtheorem\{{[^}}]+\}}(?:\[[^\]]*\])?(?:\{{\{{?[^}}]*\}}?\}})?(?:\[[^\]]*\])?',
            replacement='',
            handler=self._handle_newtheorem
        ))
        
        self.patterns.append(CommandPattern(
            name='twocolumn',
            pattern=r'\\twocolumn\[',
            replacement='',
            handler=self._handle_twocolumn
        ))
    
    def process(self, content: str) -> str:
        """Process all registered patterns against content."""
        for pattern_def in self.patterns:
            if pattern_def.handler:
                content = pattern_def.handler(content, pattern_def)
            else:
                content = re.sub(
                    pattern_def.pattern,
                    pattern_def.replacement,
                    content,
                    flags=pattern_def.flags
                )
        
        # Clean up raw_tex attributes from pandoc
        content = re.sub(r'`[^`]*`\{=latex\}', '', content)
        
        return content
    
    def _handle_newtheorem(self, content: str, pattern_def: CommandPattern) -> str:
        """Handle newtheorem definitions (with optional args and double braces)."""
        return re.sub(pattern_def.pattern, pattern_def.replacement, content)
    
    def _handle_twocolumn(self, content: str, pattern_def: CommandPattern) -> str:
        """Remove twocolumn wrapper but keep inner content."""
        pattern = r'\\twocolumn\['
        result = []
        i = 0
        
        while i < len(content):
            match = re.search(pattern, content[i:])
            if not match:
                result.append(content[i:])
                break
            
            result.append(content[i:i + match.start()])
            
            # Find matching closing bracket
            start = i + match.end()
            bracket_count = 1
            j = start
            
            while j < len(content) and bracket_count > 0:
                if content[j] == '[':
                    bracket_count += 1
                elif content[j] == ']':
                    bracket_count -= 1
                j += 1
            
            # Append inner content (j-1 because j is past the closing bracket)
            if bracket_count == 0:
                inner_content = content[start:j-1]
                result.append(inner_content)
            else:
                result.append(content[start:])
                break
            
            i = j
        
        return ''.join(result)
    
    def remove_nested_command(self, content: str, cmd: str) -> str:
        """Remove a LaTeX command with potentially nested braces.
        
        Handles commands that may span multiple lines and have nested braces.
        Also handles optional arguments like \\command[opt]{...}
        
        Args:
            content: LaTeX content
            cmd: Command name without backslash
            
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
            
            # Append content before command
            result.append(content[i:i + match.start()])
            
            # Find matching closing brace
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
    
    def remove_newcommand_definitions(self, content: str) -> str:
        """Remove \\newcommand, \\renewcommand, \\providecommand definitions.
        
        These have a special structure: \\cmd{\\name}[nargs]{definition}
        where nargs is optional and there can be multiple definition blocks.
        """
        cmd_types = ['newcommand', 'renewcommand', 'providecommand', 'DeclareMathOperator']
        
        for cmd_type in cmd_types:
            # Pattern matches: \\cmd{\\name} or \\cmd{\\name}[nargs]
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
                
                # Find all definition blocks
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
                            j += 1
                            # Check for another brace block
                            if j < len(content) and content[j] == '{':
                                in_brace = False
                                continue
                            break
                    j += 1
                
                i = j
            
            content = ''.join(result)
        
        return content


class LaTeXConverter:
    """Convert LaTeX to Markdown using Pandoc."""
    
    # Author-related commands that need nested brace handling
    AUTHOR_COMMANDS = [
        'email', 'affiliation', 'institute', 'address', 
        'thanks', 'author', 'affiliation',
    ]
    
    # ICML-specific nested commands
    ICML_NESTED_COMMANDS = [
        'icmltitle', 'icmltitlerunning', 'icmlauthor',
        'icmlaffiliation', 'icmlcorrespondingauthor',
    ]
    
    # Graphics/color commands with nested braces
    GRAPHICS_COMMANDS = [
        'usetikzlibrary', 'tikzset', 'pgfplotsset',
        'definecolor', 'color', 'colorlet',
        'keyword', 'keywords', 'pacs', 'pagecolor',
    ]
    
    def __init__(self, bib_handler: Optional[BibliographyHandler] = None, equation_numbers: Optional[dict] = None):
        self.bib_handler = bib_handler
        self.equation_numbers = equation_numbers or {}
        self.command_processor = LaTeXCommandProcessor()
    
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
        
        Uses the LaTeXCommandProcessor for systematic command removal.
        """
        # Apply standard command patterns
        content = self.command_processor.process(content)
        
        # Remove \\newcommand/\\renewcommand definitions
        content = self.command_processor.remove_newcommand_definitions(content)
        
        # Handle author information commands with nested braces
        for cmd in self.AUTHOR_COMMANDS:
            content = self.command_processor.remove_nested_command(content, cmd)
        
        # Handle ICML nested commands
        for cmd in self.ICML_NESTED_COMMANDS:
            content = self.command_processor.remove_nested_command(content, cmd)
        
        # Handle graphics commands with nested braces
        for cmd in self.GRAPHICS_COMMANDS:
            content = self.command_processor.remove_nested_command(content, cmd)
        
        # Remove bibunit environment markers
        content = re.sub(r'\\begin\{bibunit\}', '', content)
        content = re.sub(r'\\end\{bibunit\}', '', content)
        
        return content
    
    def _postprocess_citations(self, content: str) -> str:
        """Post-process citation keys in markdown output.
        
        Converts Pandoc citation format [@key] to markdown links.
        """
        if not self.bib_handler:
            return content
        
        # Store reference to avoid None checks in nested functions
        bib_handler = self.bib_handler
        
        # Handle multiple citations: [@key1; @key2; @key3]
        multi_cite_pattern = r'\[(@[a-zA-Z0-9_-]+(?:;\s*@[a-zA-Z0-9_-]+)*)\]'
        
        def replace_multi_cite(match):
            cites_str = match.group(1)
            keys = re.findall(r'@([a-zA-Z0-9_-]+)', cites_str)
            formatted = []
            for key in keys:
                if key in bib_handler.citations:
                    formatted.append(bib_handler.format_citation_markdown(key))
                else:
                    formatted.append(f'[@{key}]')
            return '; '.join(formatted) if formatted else match.group(0)
        
        content = re.sub(multi_cite_pattern, replace_multi_cite, content)
        
        # Handle single citations: [@key]
        single_cite_pattern = r'\[@([a-zA-Z0-9_-]+)\]'
        
        def replace_single_cite(match):
            key = match.group(1)
            if key in bib_handler.citations:
                return bib_handler.format_citation_markdown(key)
            return match.group(0)
        
        content = re.sub(single_cite_pattern, replace_single_cite, content)
        
        return content
    
    def _preprocess_references(self, content: str) -> str:
        r"""Pre-process reference commands (\ref, \eqref, etc.).
        
        For equations: Converts \label{eq:label} to equation number tags and 
        \ref{eq:label}/\eqref{eq:label} to markdown links with equation numbers.
        For other references: Converts to just the reference type name.
        """
        # Handle equation environments first - add equation numbers and anchors
        # Match equation environments with optional labels inside
        eq_env_pattern = r'\\begin\{(equation|align|align\*|gather|gather\*)\}(.*?)\\end\{\1\}'
        
        def process_equation_env(match):
            env_type = match.group(1)
            env_content = match.group(2)
            
            # Check for label in the equation content
            label_match = re.search(r'\\label\{(eq:[^}]+)\}', env_content)
            if label_match:
                label = label_match.group(1)
                if label in self.equation_numbers:
                    eq_num = self.equation_numbers[label]
                    # Remove the label from inside the equation and add tag outside
                    env_content_clean = re.sub(r'\\label\{[^}]+\}', '', env_content)
                    # Return equation with number tag and HTML anchor
                    return f'\\begin{{{env_type}}}{env_content_clean}\\tag{{{eq_num}}}<a name="{label}"></a>\\end{{{env_type}}}'
            
            # No label found, return as-is
            return match.group(0)
        
        content = re.sub(eq_env_pattern, process_equation_env, content, flags=re.DOTALL)
        
        # Handle equation references (\eqref{eq:label} and \ref{eq:label})
        eq_ref_pattern = r'\\(?:eq)?ref\{(eq:[^}]+)\}'
        
        def replace_eq_ref(match):
            label = match.group(1)
            if label in self.equation_numbers:
                eq_num = self.equation_numbers[label]
                return f'[({eq_num})](#{label})'
            # Fallback to plain label if not found
            return f'[{label}]'
        
        content = re.sub(eq_ref_pattern, replace_eq_ref, content)
        
        # Match patterns like "Equation \ref{...}", "Fig. \ref{...}", etc. for non-equation refs
        ref_context_pattern = r'(Equation|Eq\.?|Fig\.?|Figure|Table|Tab\.?|Section|Sec\.)\s*\\(?:eq)?ref\{[^}]+\}'
        
        def replace_ref_context(match):
            ref_type = match.group(1)
            # Normalize abbreviations
            ref_lower = ref_type.lower()
            if ref_lower in ['eq.', 'eq']:
                return 'Equation'
            elif ref_lower in ['fig.', 'fig']:
                return 'Figure'
            elif ref_lower in ['tab.', 'tab']:
                return 'Table'
            elif ref_lower in ['sec.', 'sec']:
                return 'Section'
            return ref_type
        
        content = re.sub(ref_context_pattern, replace_ref_context, content, flags=re.IGNORECASE)
        
        # Remove any remaining bare \ref{...} or \eqref{...}
        content = re.sub(r'\\(?:eq)?ref\{[^}]+\}', '', content)
        
        # Remove remaining \label commands
        content = re.sub(r'\\label\{[^}]+\}', '', content)
        
        return content
