#!/usr/bin/env python3
"""Debug script to see what's being sent to pandoc."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from arxiv_to_md.downloader import download_source, extract_arxiv_id, find_main_tex, find_bibliography_files
from arxiv_to_md.parser import LaTeXParser

# Download
arxiv_id = "1706.03762"
output_dir = Path("/tmp/debug_arxiv")
output_dir.mkdir(exist_ok=True)

try:
    source_dir = download_source(arxiv_id, output_dir)
    main_tex = find_main_tex(source_dir)
    
    print(f"Main tex: {main_tex}")
    
    parser = LaTeXParser(main_tex)
    main_content, _, _ = parser.split_document()
    
    # Save to file for inspection
    debug_file = output_dir / "debug_input.tex"
    debug_file.write_text(main_content)
    print(f"Saved content to: {debug_file}")
    
    # Show line 112
    lines = main_content.split('\n')
    print(f"\nTotal lines: {len(lines)}")
    if len(lines) > 112:
        print(f"\nLine 110: {lines[109]}")
        print(f"Line 111: {lines[110]}")
        print(f"Line 112: {lines[111]}")
        print(f"Line 113: {lines[112]}")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
