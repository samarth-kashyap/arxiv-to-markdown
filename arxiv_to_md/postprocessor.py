"""Module for post-processing markdown output."""

import re
from pathlib import Path
from typing import Optional, Tuple


class MarkdownPostProcessor:
    """Post-process markdown for token efficiency and cleanliness."""
    
    def __init__(self):
        pass
    
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
        content = self._cleanup_content(content)
        
        # Simplify math notation
        content = self._simplify_math(content)
        
        # Clean up figure references
        content = self._clean_figures(content)
        
        # Add bibliography if provided
        if bibliography:
            content = content.rstrip() + '\n' + bibliography
        
        return content.strip()
    
    def _cleanup_content(self, content: str) -> str:
        """Clean up markdown content.
        
        Removes LaTeX comments but preserves content in math environments.
        """
        lines = content.split('\n')
        cleaned_lines = []
        in_math = False
        
        for line in lines:
            # Track math environments
            if '$$' in line:
                # Toggle math mode
                count = line.count('$$')
                if count % 2 == 1:
                    in_math = not in_math
            elif '$' in line and '$$' not in line:
                # Check if it's a single $ (inline math)
                # Count unescaped $ signs
                count = len(re.findall(r'(?<!\\)\$', line))
                if count % 2 == 1:
                    in_math = not in_math
            
            if not in_math:
                # Remove LaTeX comments (but not in math)
                line = re.sub(r'(?<!\\)%.*?$', '', line)
            
            cleaned_lines.append(line)
        
        content = '\n'.join(cleaned_lines)
        
        # Collapse multiple blank lines
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        # Remove trailing whitespace
        content = re.sub(r'[ \t]+$', '', content, flags=re.MULTILINE)
        
        return content
    
    def _simplify_math(self, content: str) -> str:
        """Simplify mathematical notation for token efficiency.
        
        Only modifies LaTeX commands outside of math content.
        """
        # Replace \boldsymbol{x} with \mathbf{x}
        content = re.sub(r'\\boldsymbol\{([^}]+)\}', r'\\mathbf{\1}', content)
        
        # Replace \operatorname{name} with just name
        content = re.sub(r'\\operatorname\{([^}]+)\}', r'\1', content)
        
        # Simplify \left( ... \right) to ( ... )
        # But be careful with nested structures
        content = re.sub(r'\\left\(', '(', content)
        content = re.sub(r'\\right\)', ')', content)
        content = re.sub(r'\\left\[', '[', content)
        content = re.sub(r'\\right\]', ']', content)
        content = re.sub(r'\\left\{', '{', content)
        content = re.sub(r'\\right\}', '}', content)
        
        # Simplify simple fractions in inline math
        def simplify_frac(match):
            num = match.group(1).strip()
            den = match.group(2).strip()
            # Only simplify if both are simple (single char or number)
            if len(num) <= 2 and len(den) <= 2 and '/' not in num and '/' not in den:
                # Check if numeric
                if num.isdigit() and den.isdigit():
                    return f'{num}/{den}'
                # Check if simple variable
                if num.isalpha() and den.isalpha() and len(num) == 1 and len(den) == 1:
                    return f'{num}/{den}'
            return match.group(0)
        
        content = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', simplify_frac, content)
        
        return content
    
    def _clean_figures(self, content: str) -> str:
        """Clean up figure references since we're skipping figures."""
        # Replace figure markdown with placeholders
        # ![caption](path) -> [Figure: caption]
        fig_pattern = r'!\[([^\]]*)\]\([^)]+\)'
        content = re.sub(fig_pattern, r'[Figure: \1]', content)
        
        # Remove width/height attributes from images
        content = re.sub(r'\{width=[^}]+\}', '', content)
        content = re.sub(r'\{height=[^}]+\}', '', content)
        
        # Clean up empty figure placeholders
        content = re.sub(r'\[Figure:\s*\]', '[Figure]', content)
        
        return content
    
    def split_appendix(self, content: str) -> Tuple[str, Optional[str]]:
        """Split content into main body and appendix.
        
        Returns:
            Tuple of (main_content, appendix_content or None)
        """
        # Look for appendix heading patterns
        appendix_patterns = [
            r'^#{1,6}\s*Appendix',
            r'^#{1,6}\s*A\.\s+\w',  # "A. Title"
            r'^#{1,6}\s*A\s+\w',    # "A Title"
        ]
        
        lines = content.split('\n')
        appendix_start = None
        
        for i, line in enumerate(lines):
            for pattern in appendix_patterns:
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
