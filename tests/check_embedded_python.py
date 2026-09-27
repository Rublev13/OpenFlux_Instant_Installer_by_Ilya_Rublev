"""Compile Python heredocs without executing the installer or their contents.

Автор установщика: Илья Рублев
https://t.me/Rublev_YouTube
https://boosty.to/rublev13
https://www.youtube.com/@Ilya_Rublev
"""

from pathlib import Path
import re


source = Path(__file__).resolve().parents[1] / "openflux-install.sh"
lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
blocks = 0
index = 0
while index < len(lines):
    if re.search(r"<<'PY'\s*$", lines[index]):
        start = index + 1
        index = start
        while index < len(lines) and lines[index].rstrip("\r\n") != "PY":
            index += 1
        if index == len(lines):
            raise SystemExit(f"Unclosed Python heredoc at line {start}")
        compile("".join(lines[start:index]), f"{source.name}:{start + 1}", "exec")
        blocks += 1
    index += 1

if not blocks:
    raise SystemExit("No Python heredocs found; review this checker.")
print(f"Python syntax OK: {blocks} embedded blocks; nothing executed.")
