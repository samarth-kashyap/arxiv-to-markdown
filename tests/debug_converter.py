import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from arxiv_to_md.downloader import download_source, find_main_tex
from arxiv_to_md.parser import LaTeXParser
from arxiv_to_md.converter import LaTeXConverter

output_dir = Path("/tmp/debug_arxiv")
source_dir = output_dir / "source"
main_tex = find_main_tex(source_dir)

parser = LaTeXParser(main_tex)
main_content, _, _ = parser.split_document()

# Save the content before conversion
pre_convert = output_dir / "pre_convert.tex"
pre_convert.write_text(main_content)
print(f"Saved pre-conversion content to: {pre_convert}")

# Try to convert
converter = LaTeXConverter()
processed = converter._preprocess_commands(main_content)
processed = converter._preprocess_references(processed)

# Save processed content
post_process = output_dir / "post_process.tex"
post_process.write_text(processed)
print(f"Saved post-processed content to: {post_process}")

# Show lines around 112
lines = processed.split('\n')
print(f"\nTotal lines: {len(lines)}")
if len(lines) > 112:
    for i in range(109, min(115, len(lines))):
        print(f"Line {i+1}: {lines[i]}")
