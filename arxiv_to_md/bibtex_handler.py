"""Module for handling bibliography and citations."""

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class Citation:
    """Represents a citation entry."""
    key: str
    authors: List[str]
    year: str
    title: str
    arxiv_id: Optional[str] = None
    doi: Optional[str] = None
    journal: Optional[str] = None
    
    def format_author_year(self) -> str:
        """Format as 'Author et al., Year'.
        
        Handles various author name formats including:
        - "John Smith" -> "Smith, Year"
        - "J. Smith" -> "Smith, Year"  
        - "Smith, John" -> "Smith, Year"
        - "van der Waals, J.D." -> "van der Waals, Year"
        """
        if not self.authors:
            return f"[{self.key}]"
        
        # Clean up LaTeX commands from author names
        clean_authors = []
        for author in self.authors:
            # Remove common LaTeX font commands
            author = re.sub(r'\\bib(fname)?namefont\{([^}]+)\}', r'\2', author)
            author = re.sub(r'\\[a-zA-Z]+\{([^}]+)\}', r'\1', author)
            author = author.replace('~', ' ').strip()
            if author:
                clean_authors.append(author)
        
        if not clean_authors:
            return f"[{self.key}]"
        
        if len(clean_authors) == 1:
            author = self._extract_last_name(clean_authors[0])
            return f"{author}, {self.year}"
        elif len(clean_authors) == 2:
            author1 = self._extract_last_name(clean_authors[0])
            author2 = self._extract_last_name(clean_authors[1])
            return f"{author1} & {author2}, {self.year}"
        else:
            author = self._extract_last_name(clean_authors[0])
            return f"{author} et al., {self.year}"
    
    def _extract_last_name(self, author: str) -> str:
        """Extract last name from author string.
        
        Handles formats like:
        - "John Smith" -> "Smith"
        - "Smith, John" -> "Smith"
        - "J. Smith" -> "Smith"
        - "van der Waals, J.D." -> "van der Waals"
        """
        author = author.strip()
        if ',' in author:
            # Format: "Last, First" or "van der Waals, J.D."
            return author.split(',')[0].strip()
        else:
            # Format: "First Last" or "J. Smith"
            parts = author.split()
            if len(parts) == 1:
                return parts[0]
            # Check for multi-word last names (particles like van, de, etc.)
            particles = ['van', 'de', 'der', 'den', 'di', 'da', 'del', 'dos', 'du', 'la', 'le', 'ten', 'ter', 'von']
            if len(parts) >= 3 and parts[-2].lower() in particles:
                return f"{parts[-2]} {parts[-1]}"
            return parts[-1]
    
    def get_link(self) -> Optional[str]:
        """Get the best available link."""
        if self.arxiv_id:
            return f"https://arxiv.org/abs/{self.arxiv_id}"
        elif self.doi:
            return f"https://doi.org/{self.doi}"
        return None


class BibliographyHandler:
    """Handle bibliography parsing and citation resolution."""
    
    def __init__(self, bbl_path: Optional[Path] = None, bib_path: Optional[Path] = None):
        self.citations: Dict[str, Citation] = {}
        self.bbl_path = bbl_path
        self.bib_path = bib_path
        
        if bbl_path:
            self._parse_bbl(bbl_path)
        elif bib_path:
            self._parse_bib(bib_path)
    
    def _parse_bbl(self, bbl_path: Path):
        """Parse .bbl file (LaTeX bibliography)."""
        try:
            content = bbl_path.read_text(encoding='utf-8', errors='ignore')
        except (IOError, OSError) as e:
            return
        
        # Pattern for bibitem entries
        bibitem_pattern = r'\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}(.*?)(?=\\bibitem|\\end\{thebibliography\}|\Z)'
        
        for match in re.finditer(bibitem_pattern, content, re.DOTALL):
            key = match.group(1)
            entry_text = match.group(2).strip()
            
            if not entry_text:
                continue
            
            citation = self._extract_from_bbl_entry(key, entry_text)
            if citation:
                self.citations[key] = citation
    
    def _extract_from_bbl_entry(self, key: str, entry_text: str) -> Optional[Citation]:
        """Extract citation info from bbl entry text."""
        # Clean up entry text
        entry_text = entry_text.strip()
        if not entry_text:
            return None
        
        authors = []
        year = ""
        title = ""
        arxiv_id = None
        doi = None
        
        # Extract year - look for year in common positions
        # Try to find year at end of entry, often preceded by comma
        year_match = re.search(r',\s*(\d{4})\s*[.\s]*$', entry_text.strip())
        if not year_match:
            # Look for year followed by period
            year_match = re.search(r',\s*(\d{4})\s*\.', entry_text)
        if not year_match:
            # Look for year in the last line
            lines = entry_text.split('\n')
            for line in reversed(lines):
                year_match = re.search(r'\b((?:19|20)\d{2})\b', line)
                if year_match:
                    break
        if year_match:
            year = year_match.group(1)
        
        # Extract title - handle \bibinfo{title}{...} format
        title_patterns = [
            r'\\bibinfo\{title\}\{([^}]+)\}',
            r'\\textit\{([^}]+)\}',
            r'\\emph\{([^}]+)\}',
            r'\\newblock\s+([^.]+)\.',
            r'``([^\']+)\'\'',
            r'"([^"]+)"',
        ]
        for pattern in title_patterns:
            title_match = re.search(pattern, entry_text)
            if title_match:
                title = title_match.group(1).strip()
                # Clean up any remaining LaTeX in title
                title = re.sub(r'\\[a-zA-Z]+\{([^}]+)\}', r'\1', title)
                title = title.replace('~', ' ')
                break
        
        # Look for arXiv ID
        arxiv_match = re.search(r'ar[Xx]iv:(\d{4}\.\d+)', entry_text)
        if arxiv_match:
            arxiv_id = arxiv_match.group(1)
        
        # Look for DOI
        doi_patterns = [
            r'https?://doi\.org/([^\s,]+)',
            r'doi\.org/([^\s,]+)',
            r'DOI:\s*([^\s,]+)',
            r'\\doi\{([^}]+)\}',
        ]
        for pattern in doi_patterns:
            doi_match = re.search(pattern, entry_text)
            if doi_match:
                doi = doi_match.group(1).strip()
                break
        
        # Extract author names - handle \bibinfo{author}{...} format
        # Authors are typically before \newblock or at the start
        author_section = entry_text
        if '\\newblock' in entry_text:
            author_section = entry_text.split('\\newblock')[0]
        
        # Extract authors - handle APS-style bibitem format with \bibinfo{author}{\bibfnamefont{...}~\bibnamefont{...}}
        authors = []
        
        # First try to match the full author block pattern with ~ separator
        # Pattern: \bibinfo{author}{\bibfnamefont{Initial.}~\bibnamefont{Lastname}}
        full_author_pattern = r'\\bibinfo\{author\}\{\\bibfnamefont\{([^}]+)\}[~\s]*\\bibnamefont\{([^}]+)\}\}'
        for match in re.finditer(full_author_pattern, author_section):
            first = match.group(1).strip()
            last = match.group(2).strip()
            # Clean up any remaining commands
            first = re.sub(r'\\[a-zA-Z]+\{([^}]+)\}', r'\1', first)
            last = re.sub(r'\\[a-zA-Z]+\{([^}]+)\}', r'\1', last)
            if last:
                authors.append(f"{first} {last}" if first else last)
        
        # If no full authors found, try simpler pattern
        if not authors:
            bibinfo_author_pattern = r'\\bibinfo\{author\}\{([^}]+)\}'
            for match in re.finditer(bibinfo_author_pattern, author_section):
                author_text = match.group(1)
                # Clean up author text - remove all LaTeX commands
                author_text = re.sub(r'\\bib(fname)?namefont\{([^}]+)\}', r'\2', author_text)
                author_text = re.sub(r'\\[a-zA-Z]+\{([^}]+)\}', r'\1', author_text)
                author_text = author_text.replace('~', ' ')
                author_text = author_text.strip()
                # Remove trailing punctuation that might have been left
                author_text = re.sub(r'[,;]+$', '', author_text).strip()
                if author_text and len(author_text) > 1 and author_text not in ['and', '']:
                    authors.append(author_text)
        
        # If no bibinfo authors found, try old method
        if not authors:
            # Clean up LaTeX commands from author section
            author_section = re.sub(r'\\[a-zA-Z]+\*?(?:\{[^}]*\})*', '', author_section)
            author_section = author_section.replace('~', ' ')
            author_section = author_section.strip()
            
            # Split authors
            # Try "and" separator first, then comma
            if ' and ' in author_section.lower():
                parts = re.split(r'\s+and\s+', author_section, flags=re.IGNORECASE)
            else:
                parts = [p.strip() for p in author_section.split(',')]
            
            authors = [p for p in parts if p and len(p) > 1 and not p.startswith('{')]
        
        # Limit to first 3 authors
        authors = authors[:3]
        
        return Citation(
            key=key,
            authors=authors,
            year=year or "",
            title=title,
            arxiv_id=arxiv_id,
            doi=doi
        )
    
    def _parse_bib(self, bib_path: Path):
        """Parse .bib file using bibtexparser."""
        try:
            import bibtexparser
            
            with open(bib_path, 'r', encoding='utf-8', errors='ignore') as f:
                bib_database = bibtexparser.load(f)
            
            for entry in bib_database.entries:
                self._add_bib_entry(entry)
                
        except ImportError:
            # Fallback to simple regex parsing
            self._parse_bib_simple(bib_path)
        except Exception as e:
            # Log error but continue
            pass
    
    def _add_bib_entry(self, entry: Dict):
        """Add a bib entry to citations."""
        key = entry.get('ID', '')
        if not key:
            return
        
        authors_str = entry.get('author', '')
        authors = [a.strip() for a in authors_str.split(' and ') if a.strip()]
        
        # Try to find arxiv ID from various fields
        arxiv_id = entry.get('arxivId') or entry.get('eprint', '')
        if arxiv_id and not arxiv_id.startswith('http'):
            arxiv_id = arxiv_id.replace('arXiv:', '').strip()
        
        # Clean up title
        title = entry.get('title', '').replace('{', '').replace('}', '')
        
        self.citations[key] = Citation(
            key=key,
            authors=authors[:3],
            year=entry.get('year', ''),
            title=title,
            arxiv_id=arxiv_id if arxiv_id else None,
            doi=entry.get('doi', None)
        )
    
    def _parse_bib_simple(self, bib_path: Path):
        """Simple regex-based bib parsing as fallback."""
        try:
            content = bib_path.read_text(encoding='utf-8', errors='ignore')
        except (IOError, OSError):
            return
        
        # Match @type{key, ... } entries (handle nested braces)
        entry_pattern = r'@\w+\s*\{([^,]+),\s*([^@]+?)(?=@[^@]+\{|\Z)'
        
        for match in re.finditer(entry_pattern, content, re.DOTALL):
            key = match.group(1).strip()
            fields_text = match.group(2)
            
            entry = {'ID': key}
            
            # Extract fields with nested brace handling
            field_pattern = r'(\w+)\s*=\s*(\{[^}]*\}|"[^"]*"|\d+)'
            for fm in re.finditer(field_pattern, fields_text):
                field_name = fm.group(1).lower()
                field_value = fm.group(2)
                
                # Remove braces or quotes
                if field_value.startswith('{') and field_value.endswith('}'):
                    field_value = field_value[1:-1]
                elif field_value.startswith('"') and field_value.endswith('"'):
                    field_value = field_value[1:-1]
                
                entry[field_name] = field_value
            
            self._add_bib_entry(entry)
    
    def lookup_arxiv_metadata(
        self, 
        arxiv_id: str, 
        max_retries: int = 2,
        retry_delay: float = 1.0
    ) -> Optional[Citation]:
        """Fetch citation metadata from arXiv API.
        
        Args:
            arxiv_id: arXiv paper ID
            max_retries: Maximum retry attempts
            retry_delay: Delay between retries
            
        Returns:
            Citation object or None if lookup fails
        """
        try:
            import arxiv as arxiv_lib
            
            for attempt in range(max_retries):
                try:
                    search = arxiv_lib.Search(id_list=[arxiv_id])
                    paper = next(search.results())
                    
                    return Citation(
                        key=arxiv_id,
                        authors=[str(a) for a in paper.authors][:3],
                        year=str(paper.published.year),
                        title=paper.title,
                        arxiv_id=arxiv_id,
                        doi=paper.doi
                    )
                except arxiv_lib.HTTPError as e:
                    if e.status_code == 429 and attempt < max_retries - 1:
                        time.sleep(retry_delay * (attempt + 1))
                        continue
                    raise
                    
        except Exception:
            return None
    
    def resolve_citation(self, key: str) -> Optional[Citation]:
        """Get citation by key, with lookup fallback.
        
        Args:
            key: Citation key
            
        Returns:
            Citation object or None
        """
        if key in self.citations:
            return self.citations[key]
        
        # Try to lookup as arxiv ID
        if re.match(r'^\d{4}\.\d+$', key):
            citation = self.lookup_arxiv_metadata(key)
            if citation:
                self.citations[key] = citation
                return citation
        
        return None
    
    def format_citation_markdown(self, key: str) -> str:
        """Format citation as markdown link.
        
        Args:
            key: Citation key
            
        Returns:
            Markdown formatted citation
        """
        citation = self.resolve_citation(key)
        
        if not citation:
            return f"[{key}]"
        
        author_year = citation.format_author_year()
        link = citation.get_link()
        
        if link:
            return f"[{author_year}]({link})"
        return author_year
    
    def generate_bibliography(self) -> str:
        """Generate brief bibliography with links.
        
        Returns:
            Markdown formatted bibliography section
        """
        if not self.citations:
            return ""
        
        lines = ["\n## References\n"]
        
        for key, citation in sorted(self.citations.items()):
            author_year = citation.format_author_year()
            link = citation.get_link()
            
            # Clean up title for markdown - remove LaTeX commands
            title = citation.title
            if title:
                # Remove \bibinfo{title}{...} and similar commands
                title = re.sub(r'\\bibinfo\{title\}\{([^}]+)\}', r'\1', title)
                title = re.sub(r'\\[a-zA-Z]+\{([^}]+)\}', r'\1', title)
                title = title.replace('~', ' ').strip()
                if link:
                    lines.append(f"- {author_year}. *{title}*. [{key}]({link})")
                else:
                    lines.append(f"- {author_year}. *{title}*.")
            else:
                if link:
                    lines.append(f"- {author_year}. [{key}]({link})")
                else:
                    lines.append(f"- {author_year}.")
        
        return '\n'.join(lines)
