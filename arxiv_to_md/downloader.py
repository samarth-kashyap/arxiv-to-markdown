"""Module for downloading and extracting arXiv source files."""

import re
import shutil
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Optional, Tuple

import arxiv


class ArxivDownloadError(Exception):
    """Custom exception for arXiv download failures."""
    pass


def extract_arxiv_id(input_str: str) -> str:
    """Extract arXiv ID from various input formats.
    
    Handles:
    - 2401.12345
    - arXiv:2401.12345
    - https://arxiv.org/abs/2401.12345
    - https://arxiv.org/pdf/2401.12345.pdf
    - Version suffixes: 2401.12345v1
    
    Raises:
        ValueError: If arXiv ID cannot be extracted
    """
    patterns = [
        (r'arxiv\.org/abs/(\d+\.\d+)', 1),
        (r'arxiv\.org/pdf/(\d+\.\d+)\.pdf', 1),
        (r'ar[Xx]iv:(\d+\.\d+)', 1),
        (r'^(\d+\.\d+)$', 1),
        (r'^(\d+\.\d+)v\d+$', 1),
    ]
    
    for pattern, group in patterns:
        match = re.search(pattern, input_str)
        if match:
            return match.group(group)
    
    raise ValueError(
        f"Could not extract arXiv ID from: {input_str}. "
        f"Expected formats: '2401.12345', 'arXiv:2401.12345', "
        f"'https://arxiv.org/abs/2401.12345'"
    )


def download_source(
    arxiv_id: str, 
    output_dir: Optional[Path] = None,
    max_retries: int = 3,
    retry_delay: float = 5.0
) -> Path:
    """Download and extract arXiv source files.
    
    Args:
        arxiv_id: Clean arXiv ID (e.g., "2401.12345")
        output_dir: Directory to extract to (default: temp directory)
        max_retries: Maximum number of download retries
        retry_delay: Delay between retries in seconds
        
    Returns:
        Path to extracted source directory
        
    Raises:
        ArxivDownloadError: If download fails after all retries
        FileNotFoundError: If no .tex files found in source
    """
    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix=f"arxiv_{arxiv_id}_"))
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
    
    source_path = output_dir / f"{arxiv_id}_source.tar.gz"
    extract_dir = output_dir / "source"
    extract_dir.mkdir(exist_ok=True)
    
    last_error = None
    for attempt in range(max_retries):
        try:
            # Search for paper
            search = arxiv.Search(id_list=[arxiv_id])
            paper = next(search.results())
            
            # Download source
            download_dir = output_dir / f"download_{attempt}"
            download_dir.mkdir(exist_ok=True)
            
            try:
                downloaded = paper.download_source(download_dir)
                if downloaded:
                    downloaded_path = Path(downloaded)
                    if downloaded_path.exists():
                        # Move to our target location
                        if downloaded_path.is_dir():
                            # Sometimes it returns a directory
                            shutil.move(str(downloaded_path), str(source_path))
                        else:
                            shutil.move(str(downloaded_path), str(source_path))
            finally:
                # Clean up download directory
                if download_dir.exists():
                    shutil.rmtree(download_dir, ignore_errors=True)
            
            # Verify download succeeded
            if not source_path.exists() or source_path.stat().st_size == 0:
                raise ArxivDownloadError(f"Downloaded file is empty or missing: {source_path}")
            
            # Extract tarball
            try:
                with tarfile.open(source_path, 'r:gz') as tar:
                    tar.extractall(path=extract_dir)
            except tarfile.TarError as e:
                raise ArxivDownloadError(f"Failed to extract tarball: {e}")
            
            # Clean up tarball
            source_path.unlink(missing_ok=True)
            
            # Verify extraction succeeded
            if not any(extract_dir.iterdir()):
                raise ArxivDownloadError("Extracted directory is empty")
            
            return extract_dir
            
        except StopIteration:
            last_error = ArxivDownloadError(f"Paper with ID {arxiv_id} not found on arXiv")
        except arxiv.HTTPError as e:
            if e.status_code == 429:
                last_error = ArxivDownloadError(f"Rate limited by arXiv (HTTP 429)")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                    continue
            else:
                last_error = ArxivDownloadError(f"HTTP error: {e}")
        except Exception as e:
            last_error = ArxivDownloadError(f"Download error: {e}")
        
        if attempt < max_retries - 1:
            time.sleep(retry_delay)
    
    # Clean up on failure
    if output_dir.exists():
        shutil.rmtree(output_dir, ignore_errors=True)
    
    raise last_error or ArxivDownloadError("Failed to download source after all retries")


def find_main_tex(source_dir: Path) -> Path:
    """Find the main .tex file in the source directory.
    
    Looks for:
    1. main.tex
    2. paper.tex
    3. ms.tex
    4. root.tex
    5. Any .tex file with \\documentclass
    
    Args:
        source_dir: Directory containing .tex files
        
    Returns:
        Path to main .tex file
        
    Raises:
        FileNotFoundError: If no suitable .tex file found
    """
    tex_files = list(source_dir.rglob("*.tex"))
    
    if not tex_files:
        raise FileNotFoundError(f"No .tex files found in {source_dir}")
    
    # Priority list
    priority_names = ['main.tex', 'paper.tex', 'ms.tex', 'root.tex']
    for name in priority_names:
        for tf in tex_files:
            if tf.name.lower() == name:
                return tf
    
    # Look for file with \\documentclass
    for tf in tex_files:
        try:
            content = tf.read_text(encoding='utf-8', errors='ignore')
            if r'\documentclass' in content:
                return tf
        except (IOError, OSError):
            continue
    
    # Fallback to first tex file with content
    for tf in tex_files:
        try:
            if tf.stat().st_size > 0:
                return tf
        except (IOError, OSError):
            continue
    
    raise FileNotFoundError(f"No valid .tex files found in {source_dir}")


def find_bibliography_files(source_dir: Path) -> Tuple[Optional[Path], Optional[Path]]:
    """Find bibliography files.
    
    Args:
        source_dir: Directory to search
        
    Returns:
        Tuple of (bbl_path, bib_path) - either may be None
    """
    bbl_files = list(source_dir.glob("*.bbl"))
    bib_files = list(source_dir.glob("*.bib"))
    
    bbl_path = bbl_files[0] if bbl_files else None
    bib_path = bib_files[0] if bib_files else None
    
    return bbl_path, bib_path
