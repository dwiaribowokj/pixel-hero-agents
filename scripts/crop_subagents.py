"""Crop 15 hewan sub-agent dari sheet.png ke file terpisah, urut sama
dengan agents anthropomorphic (index → karakter sama)."""
from PIL import Image
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHEET = ROOT / "assets" / "subagents" / "sheet.png"
OUT_DIR = ROOT / "assets" / "subagents"
COLS, ROWS = 5, 3

img = Image.open(SHEET).convert("RGBA")
W, H = img.size
cell_w, cell_h = W // COLS, H // ROWS
print(f"Sheet: {W}×{H}, cell: {cell_w}×{cell_h}")
idx = 0
for row in range(ROWS):
    for col in range(COLS):
        cell = img.crop((col*cell_w, row*cell_h,
                         (col+1)*cell_w, (row+1)*cell_h))
        bbox = cell.getbbox()
        if bbox is None:
            idx += 1; continue
        char = cell.crop(bbox)
        char.save(OUT_DIR / f"sub_{idx}.png")
        print(f"  sub_{idx}.png  {char.size[0]}×{char.size[1]}")
        idx += 1
