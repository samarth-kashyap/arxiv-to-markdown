"""Module for post-processing markdown output."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple, Pattern


@dataclass
class CleanupPattern:
    """Definition of a cleanup pattern for markdown content.
    
    Attributes:
        name: Pattern name for identification
        pattern: Regex pattern string or compiled pattern
        replacement: Replacement string or function
        handler: Optional custom handler function
        flags: Regex flags
    """
    name: str
    pattern: str
    replacement: str = ''
    handler: Optional[Callable[[str, 'CleanupPattern'], str]] = None
    flags: int = 0
    _compiled: Optional[Pattern] = None
    
    def compile(self) -> Pattern:
        """Compile the regex pattern."""
        self._compiled = re.compile(self.pattern, self.flags)
        return self._compiled


class MarkdownCleaner:
    """Systematic markdown content cleaner.
    
    Provides organized, extensible patterns for cleaning up
    markdown output from Pandoc conversion.
    """
    
    # Patterns organized by category
    CONTENT_PATTERNS: List[CleanupPattern] = [
        # Remove LaTeX comments (outside math)
        CleanupPattern('latex_comments', r'(?<!\\)%.*?$', '', flags=re.MULTILINE),
        
        # Collapse multiple blank lines
        CleanupPattern('multiple_blank_lines', r'\n{3,}', '\n\n'),
        
        # Remove trailing whitespace
        CleanupPattern('trailing_whitespace', r'[ \t]+$', '', flags=re.MULTILINE),
        
        # Remove raw_tex attributes from pandoc
        CleanupPattern('raw_tex_attrs', r'`[^`]*`\{=latex\}', ''),
        
        # Remove RGB color definitions
        CleanupPattern('rgb_colors', r'\bRGB\d+,\d+,\d+\b', ''),
        
        # Remove LaTeX artifacts at start
        CleanupPattern('newsavebox', r'\\newsavebox\{[^}]+\}', ''),
        CleanupPattern('sbox', r'\\sbox\{[^}]+\}\{[^}]+\}', ''),
        
        # Remove frontmatter commands
        CleanupPattern('journal', r'\\journal\{[^}]+\}', ''),
        CleanupPattern('frontmatter_env', r'\\(?:begin|end)\{frontmatter\}', ''),
        CleanupPattern('abstract_env', r'\\(?:begin|end)\{abstract\}', ''),
        CleanupPattern('keyword_env', r'\\(?:begin|end)\{keyword\}', ''),
        CleanupPattern('keywords_env', r'\\(?:begin|end)\{keywords\}', ''),
        CleanupPattern('appendix_cmd', r'\\appendix', ''),
        
        # Remove counter commands
        CleanupPattern('addtoreset_full', r'\\addtoreset\{[^}]+\}\{[^}]+\}', ''),
        CleanupPattern('addtoreset_partial', r'\\addtoreset\w*', ''),
        CleanupPattern('addtoreset_at', r'\\@addtoreset\{[^}]+\}\{[^}]+\}', ''),
    ]
    
    THEOREM_ENVIRONMENTS = [
        'theorem', 'proposition', 'lemma', 'corollary', 'definition',
        'example', 'remark', 'proof', 'claim', 'conjecture', 'assertion',
        'exercise', 'assumption', 'question', 'observation', 'property',
    ]
    
    MATH_PATTERNS: List[CleanupPattern] = [
        # Simplify bold symbols
        CleanupPattern('boldsymbol', r'\\boldsymbol\{([^}]+)\}', r'\\mathbf{\1}'),

        # Remove operatorname wrapper
        CleanupPattern('operatorname', r'\\operatorname\{([^}]+)\}', r'\1'),

        # Remove ensuremath wrapper
        CleanupPattern('ensuremath', r'\\ensuremath\{([^}]+)\}', r'\1'),

        # Remove mbox wrapper
        CleanupPattern('mbox', r'\\mbox\{([^}]+)\}', r'\1'),

        # Simplify bold font commands
        CleanupPattern('bf_command', r'\\bf\s+([a-zA-Z])', r'\\mathbf{\1}'),

        # Simplify left/right delimiters
        CleanupPattern('left_paren', r'\\left\(', '('),
        CleanupPattern('right_paren', r'\\right\)', ')'),
        CleanupPattern('left_bracket', r'\\left\[', '['),
        CleanupPattern('right_bracket', r'\\right\]', ']'),
        CleanupPattern('left_brace', r'\\left\{', '{'),
        CleanupPattern('right_brace', r'\\right\}', '}'),

        # Remove align environment markers
        CleanupPattern('align_begin', r'\\begin\{align\*?\}', ''),
        CleanupPattern('align_end', r'\\end\{align\*?\}', ''),
        CleanupPattern('equation_begin', r'\\begin\{equation\*?\}', ''),
        CleanupPattern('equation_end', r'\\end\{equation\*?\}', ''),

        # Clean up extra blank lines in equations
        CleanupPattern('equation_extra_lines', r'\$\$\s*\n\s*\n+', '$$\n'),
        CleanupPattern('equation_end_lines', r'\n\s*\n+\s*\$\$', '\n$$'),
    ]
    
    FIGURE_PATTERNS: List[CleanupPattern] = [
        # Convert markdown images to placeholders
        CleanupPattern('markdown_image', r'!\[([^\]]*)\]\([^)]+\)', r'[Figure: \1]'),
        
        # Remove width/height attributes
        CleanupPattern('width_attr', r'\{width=[^}]+\}', ''),
        CleanupPattern('height_attr', r'\{height=[^}]+\}', ''),
        
        # Clean up empty placeholders
        CleanupPattern('empty_figure', r'\[Figure:\s*\]', '[Figure]'),
        
        # Convert HTML figure tags
        CleanupPattern(
            'html_figure',
            r'<figure[^>]*>.*?<figcaption>(.*?)</figcaption>.*?</figure>',
            r'[Figure: \1]',
            flags=re.DOTALL
        ),
    ]
    
    TABLE_PATTERNS: List[CleanupPattern] = [
        # Remove table commands
        CleanupPattern('centering', r'\\centering\b', ''),
        CleanupPattern('multirow', r'\\multirow\{[^}]+\}\{[^}]+\}\{([^}]+)\}', r'\1'),
        CleanupPattern('cline', r'\\cline\{[^}]+\}', ''),
        CleanupPattern('tabular_begin', r'\\begin\{tabular\}[^\n]*', ''),
        CleanupPattern('tabular_end', r'\\end\{tabular\}', ''),
        CleanupPattern('hline', r'\\hline', ''),
    ]
    
    def __init__(self):
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile all regex patterns for efficiency."""
        for pattern_list in [
            self.CONTENT_PATTERNS,
            self.MATH_PATTERNS,
            self.FIGURE_PATTERNS,
            self.TABLE_PATTERNS,
        ]:
            for pattern in pattern_list:
                if not hasattr(pattern, '_compiled'):
                    pattern._compiled = pattern.compile()
    
    def _apply_patterns(self, content: str, patterns: List[CleanupPattern]) -> str:
        """Apply a list of patterns to content."""
        for pattern_def in patterns:
            if pattern_def.handler:
                content = pattern_def.handler(content, pattern_def)
            else:
                # Ensure pattern is compiled
                compiled = pattern_def._compiled if pattern_def._compiled is not None else pattern_def.compile()
                content = compiled.sub(pattern_def.replacement, content)
        return content
    
    def clean_content(self, content: str) -> str:
        """Clean up general markdown content."""
        # Split into lines for line-by-line processing
        lines = content.split('\n')
        cleaned_lines = []
        in_math = False
        
        for line in lines:
            # Track math environments
            if '$$' in line:
                count = line.count('$$')
                if count % 2 == 1:
                    in_math = not in_math
            elif '$' in line and '$$' not in line:
                count = len(re.findall(r'(?<!\\)\$', line))
                if count % 2 == 1:
                    in_math = not in_math
            
            if not in_math:
                # Remove LaTeX comments (but not in math)
                line = re.sub(r'(?<!\\)%.*?$', '', line)
            
            cleaned_lines.append(line)
        
        content = '\n'.join(cleaned_lines)
        
        # Apply content patterns
        content = self._apply_patterns(content, self.CONTENT_PATTERNS)
        
        # Remove empty lines at start with LaTeX artifacts
        content = self._remove_start_artifacts(content)
        
        # Remove theorem environment markers
        content = self._remove_theorem_environments(content)
        
        return content
    
    def _remove_start_artifacts(self, content: str) -> str:
        """Remove LaTeX artifacts at the start of document."""
        lines = content.split('\n')
        start_idx = 0
        
        artifact_patterns = [
            '',  # Empty lines
            '=',  # Pandoc header artifacts
            'rgb',
        ]
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Check if line is an artifact
            is_artifact = False
            
            # Empty or special marker
            if stripped in artifact_patterns or stripped.startswith('= '):
                is_artifact = True
            # Starts with backslash
            elif stripped.startswith('\\'):
                is_artifact = True
            # Starts with theorem-like name (only in first 10 lines)
            elif i < 10 and stripped in self.THEOREM_ENVIRONMENTS:
                is_artifact = True
            # Bracketed theorem reference
            elif i < 10 and re.match(
                r'^[\[\]\\]+(?:' + '|'.join(self.THEOREM_ENVIRONMENTS) + r')[\[\]\\]*$',
                stripped, re.IGNORECASE
            ):
                is_artifact = True
            
            if is_artifact:
                start_idx = i + 1
            else:
                break
        
        return '\n'.join(lines[start_idx:])
    
    def _remove_theorem_environments(self, content: str) -> str:
        """Remove theorem environment begin/end markers."""
        # Build pattern for all theorem environments
        env_list = '|'.join(self.THEOREM_ENVIRONMENTS)
        pattern = rf'\\(?:begin|end)\{{({env_list})\}}'
        content = re.sub(pattern, '', content, flags=re.IGNORECASE)
        return content
    
    def clean_math(self, content: str) -> str:
        """Simplify mathematical notation."""
        content = self._apply_patterns(content, self.MATH_PATTERNS)
        
        # Simplify simple fractions
        def simplify_frac(match):
            num = match.group(1).strip()
            den = match.group(2).strip()
            
            # Only simplify simple cases
            if len(num) <= 2 and len(den) <= 2 and '/' not in num and '/' not in den:
                if num.isdigit() and den.isdigit():
                    return f'{num}/{den}'
                if num.isalpha() and den.isalpha() and len(num) == 1 and len(den) == 1:
                    return f'{num}/{den}'
            
            return match.group(0)
        
        content = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', simplify_frac, content)
        
        return content
    
    def clean_figures(self, content: str) -> str:
        """Clean up figure references."""
        return self._apply_patterns(content, self.FIGURE_PATTERNS)
    
    def clean_tables(self, content: str) -> str:
        """Clean up LaTeX table artifacts."""
        return self._apply_patterns(content, self.TABLE_PATTERNS)


class MarkdownPostProcessor:
    """Post-process markdown for token efficiency and cleanliness."""
    
    # Appendix heading patterns
    APPENDIX_PATTERNS = [
        r'^#{1,6}\s*Appendix',
        r'^#{1,6}\s*A\.\s+\w',  # "A. Title"
        r'^#{1,6}\s*A\s+\w',    # "A Title"
    ]
    
    def __init__(self):
        self.cleaner = MarkdownCleaner()
    
    def process(
        self,
        content: str,
        bibliography: Optional[str] = None
    ) -> str:
        """Process markdown content.
        
        Args:
            content: Raw markdown from pandoc
            bibliography: Bibliography text to append
            
        Returns:
            Cleaned markdown
        """
        # Apply cleanup patterns (safely)
        content = self.cleaner.clean_content(content)
        
        # Simplify math notation
        content = self.cleaner.clean_math(content)
        
        # Clean up figure references
        content = self.cleaner.clean_figures(content)
        
        # Clean up tables
        content = self.cleaner.clean_tables(content)
        
        # Add bibliography if provided
        if bibliography:
            content = content.rstrip() + '\n' + bibliography
        
        return content.strip()
    
    def split_appendix(self, content: str) -> Tuple[str, Optional[str]]:
        """Split content into main body and appendix.
        
        Returns:
            Tuple of (main_content, appendix_content or None)
        """
        lines = content.split('\n')
        appendix_start = None
        
        for i, line in enumerate(lines):
            for pattern in self.APPENDIX_PATTERNS:
                if re.match(pattern, line, re.IGNORECASE):
                    appendix_start = i
                    break
            if appendix_start is not None:
                break
        
        if appendix_start is not None:
            main = '\n'.join(lines[:appendix_start]).strip()
            appendix = '\n'.join(lines[appendix_start:]).strip()
            return main, appendix
        
        return content, None
