"""Module for parsing LaTeX structure and extracting components."""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set


class LaTeXParserError(Exception):
    """Custom exception for LaTeX parsing errors."""
    pass


class LaTeXParser:
    """Parse LaTeX document structure."""
    
    def __init__(self, tex_path: Path, max_include_depth: int = 20, source_dir: Optional[Path] = None):
        """Initialize parser.
        
        Args:
            tex_path: Path to main .tex file
            max_include_depth: Maximum depth for nested includes (prevents infinite loops)
            source_dir: Root source directory (defaults to tex_path.parent)
        """
        self.tex_path = tex_path
        self.source_dir = source_dir if source_dir else tex_path.parent
        self.max_include_depth = max_include_depth
        self._processed_files: Set[str] = set()  # Track to detect circular includes
        self.content = self._read_and_expand(tex_path)
        self.labels: Dict[str, str] = {}  # label -> type (fig, eq, sec, etc.)
        self._extract_labels()
    
    def _read_and_expand(self, tex_path: Path, depth: int = 0) -> str:
        r"""Read tex file and expand \input{} and \include{} commands.
        
        Args:
            tex_path: Path to tex file to read
            depth: Current recursion depth
            
        Returns:
            Expanded content
            
        Raises:
            LaTeXParserError: If max depth exceeded or circular include detected
        """
        if depth > self.max_include_depth:
            raise LaTeXParserError(
                f"Maximum include depth ({self.max_include_depth}) exceeded. "
                f"Possible circular includes in {tex_path}"
            )
        
        # Track file to detect circular includes
        file_key = str(tex_path.resolve())
        if file_key in self._processed_files:
            # Return empty string for circular reference
            return f"% Circular include skipped: {tex_path.name}\n"
        
        try:
            content = tex_path.read_text(encoding='utf-8', errors='ignore')
        except (IOError, OSError) as e:
            raise LaTeXParserError(f"Failed to read {tex_path}: {e}")
        
        # Mark as processed
        self._processed_files.add(file_key)
        
        # Expand \input{file} and \include{file}
        # Pattern matches: \input{filename}, \include{filename}
        # Handles both with and without .tex extension
        # Only matches at start of line or after whitespace (not in comments)
        input_pattern = r'(?<!%)\\(input|include)\{([^}]+)\}'
        
        def expand_input(match):
            cmd = match.group(1)
            filename = match.group(2)
            
            # Clean up filename
            filename = filename.strip()
            if not filename.endswith('.tex'):
                filename += '.tex'
            
            # Resolve path relative to current file's directory
            file_path = tex_path.parent / filename
            
            if not file_path.exists():
                # Try relative to source_dir as fallback
                file_path = self.source_dir / filename
            
            if file_path.exists():
                try:
                    included_content = self._read_and_expand(file_path, depth + 1)
                    return included_content
                except LaTeXParserError:
                    # Re-raise with more context
                    raise
                except Exception as e:
                    # Log and continue with placeholder
                    return f"% Error including {filename}: {e}\n"
            else:
                # File not found - add comment but don't include the original command
                return f"% Include not found: {filename}\n"
        
        # Expand iteratively to handle nested includes
        max_iterations = self.max_include_depth
        for _ in range(max_iterations):
            new_content = re.sub(input_pattern, expand_input, content)
            if new_content == content:
                break
            content = new_content
        else:
            # Did not converge - check if we still have includes
            if re.search(input_pattern, content):
                raise LaTeXParserError(
                    f"Include expansion did not converge after {max_iterations} iterations"
                )
        
        return content
    
    def _extract_labels(self):
        r"""Extract all \label{} commands and categorize them by type.
        
        Identifies which labels are inside equation environments.
        """
        label_pattern = r'\\label\{([^}]+)\}'
        equation_pattern = r'\\begin\{(equation|align|align\*|gather|gather\*|multiline|multiline\*|eqnarray|eqnarray\*)\}'
        
        lines = self.content.split('\n')
        current_eq_env = None
        in_equation = False
        
        for i, line in enumerate(lines):
            # Track equation environments
            eq_match = re.search(equation_pattern, line)
            if eq_match:
                current_eq_env = eq_match.group(1)
                in_equation = True
            
            # Check for end of equation environment
            if current_eq_env and re.search(rf'\\end\{{{re.escape(current_eq_env)}\}}', line):
                in_equation = False
                current_eq_env = None
            
            for match in re.finditer(label_pattern, line):
                label = match.group(1)
                
                # Determine type from context
                if in_equation or current_eq_env:
                    # Label is inside an equation environment
                    label_type = 'eq'
                else:
                    # Get context (3 lines before and current line)
                    start = max(0, i - 3)
                    context = '\n'.join(lines[start:i+1])
                    label_type = self._determine_label_type(context)
                
                self.labels[label] = label_type
    
    def _determine_label_type(self, context: str) -> str:
        """Determine the type of label from its context.
        
        Args:
            context: Surrounding LaTeX content (3 lines before + current line)
            
        Returns:
            Type string: 'sec', 'eq', 'fig', 'tab', or 'ref'
        """
        context_lower = context.lower()
        lines = context_lower.split('\n')
        
        # Get the current line (last line in context)
        current_line = lines[-1] if lines else ""
        
        # Check current line first for specific environments
        # Equation types
        if r'\begin{equation' in current_line or r'\[' in current_line:
            return 'eq'
        if r'\begin{align' in current_line:
            return 'eq'
        if r'\begin{gather' in current_line:
            return 'eq'
        
        # Figure types
        if r'\begin{figure' in current_line:
            return 'fig'
        
        # Table types
        if r'\begin{table' in current_line:
            return 'tab'
        
        # Section types (check full context for sections)
        # These typically appear on the same line or before the label
        if r'\subsubsection' in context_lower:
            return 'sec'
        if r'\subsection' in context_lower:
            return 'sec'
        if r'\section' in context_lower:
            return 'sec'
        if r'\chapter' in context_lower:
            return 'sec'
        
        # Figure types
        elif r'\begin{figure' in context_lower:
            return 'fig'
        
        # Table types
        elif r'\begin{table' in context_lower:
            return 'tab'
        
        # Default
        return 'ref'
    
    def split_document(self) -> Tuple[str, Optional[str], Optional[str]]:
        """Split document into main body, appendix, and bibliography.
        
        Returns:
            Tuple of (main_content, appendix_content, bibliography_content)
            appendix_content and bibliography_content may be None
        """
        content = self.content
        
        # Extract embedded bibliography if present (\begin{thebibliography}...\end{thebibliography})
        bib_env_pattern = r'(\\begin\{thebibliography\}.*?\\end\{thebibliography\})'
        bib_match = re.search(bib_env_pattern, content, re.DOTALL)
        bibliography_content = None
        if bib_match:
            bibliography_content = bib_match.group(1)
            # Remove from content for now - we'll add it back via postprocessor
            content = content[:bib_match.start()] + content[bib_match.end():]
        
        # Remove \bibliography{...} command (but not the content)
        bib_cmd_pattern = r'\\bibliography\{[^}]+\}'
        content = re.sub(bib_cmd_pattern, '', content)
        
        # Split at appendix
        appendix_markers = [
            r'\\appendix',
            r'\\begin\{appendix\}',
            r'\\begin\{appendices\}',
        ]
        
        main_content = content
        appendix_content = None
        
        for marker in appendix_markers:
            match = re.search(marker, content, re.IGNORECASE)
            if match:
                main_content = content[:match.start()]
                appendix_content = content[match.start():]
                break
        
        # Ensure main_content is a complete document
        main_content = self._ensure_complete_document(main_content)
        
        # Process appendix content if present
        if appendix_content:
            appendix_content = self._ensure_complete_document(
                appendix_content, 
                base_content=content
            )
        
        return main_content, appendix_content, bibliography_content
    
    def _ensure_complete_document(
        self, 
        content: str, 
        base_content: Optional[str] = None
    ) -> str:
        r"""Ensure content is a complete LaTeX document.
        
        Adds \documentclass, \begin{document}, \end{document} if missing.
        
        Args:
            content: Content to check/fix
            base_content: Optional base document to extract preamble from
            
        Returns:
            Complete document content
        """
        # Remove existing \end{document} if present (will add back at end)
        content = re.sub(r'\\end\{document\}', '', content)
        
        if r'\begin{document}' not in content:
            # Need to add document structure
            if base_content and r'\begin{document}' in base_content:
                # Extract preamble from base document
                preamble_match = re.search(r'(.*?)(?=\\begin\{document\})', base_content, re.DOTALL)
                if preamble_match:
                    preamble = preamble_match.group(1)
                    content = preamble + '\n\\begin{document}\n' + content
            else:
                # Add minimal document structure
                if r'\documentclass' not in content:
                    content = '\\documentclass{article}\n' + content
                content = content + '\n\\begin{document}'
        
        # Ensure \end{document} is at the end
        if r'\end{document}' not in content:
            content = content.rstrip() + '\n\\end{document}'
        
        return content
    
    def extract_citations(self) -> List[str]:
        """Extract all citation keys from the document.
        
        Returns:
            List of unique citation keys
        """
        # Match various cite commands: \cite, \citet, \citep, \citeauthor, \citeyear
        cite_pattern = r'\\cite(?:t|p|author|year)?\{([^}]+)\}'
        citations = []
        
        for match in re.finditer(cite_pattern, self.content):
            # Handle multiple keys in one cite: \cite{key1,key2,key3}
            keys = [k.strip() for k in match.group(1).split(',')]
            citations.extend(keys)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_citations = []
        for cite in citations:
            if cite not in seen:
                seen.add(cite)
                unique_citations.append(cite)
        
        return unique_citations
    
    def get_label_number(self, label: str, label_type: str) -> int:
        """Get the number for a label based on its order in the document.
        
        Args:
            label: Label name
            label_type: Type of label ('sec', 'eq', 'fig', 'tab', 'ref')
            
        Returns:
            1-based index of label among labels of same type, or 0 if not found
        """
        type_labels = [l for l, t in self.labels.items() if t == label_type]
        try:
            return type_labels.index(label) + 1
        except ValueError:
            return 0
