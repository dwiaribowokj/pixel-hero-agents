"""Crop 15 hewan sub-agent dari sheet.png ke file terpisah, urut sama
dengan agents anthropomorphic (index → karakter sama).

Pakai inner margin untuk hilangkan fragmen tetangga di tepi cell."""
from PIL import Image
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHEET = ROOT / "assets" / "subagents" / "sheet.png"
OUT_DIR = ROOT / "assets" / "subagents"
COLS, ROWS = 5, 3
MARGIN_X = 0.10   # 10% margin kiri+kanan
MARGIN_Y = 0.12   # 12% margin atas+bawah

img = Image.open(SHEET).convert("RGBA")
W, H = img.size
cell_w, cell_h = W // COLS, H // ROWS
mx = int(cell_w * MARGIN_X)
my = int(cell_h * MARGIN_Y)
print(f"Sheet: {W}×{H}, cell: {cell_w}×{cell_h}")
print(f"Inner crop margin: {mx}px × {my}px")
idx = 0
for row in range(ROWS):
    for col in range(COLS):
        x0 = col * cell_w
        y0 = row * cell_h
        inner = img.crop((x0 + mx, y0 + my,
                          x0 + cell_w - mx, y0 + cell_h - my))
        bbox = inner.getbbox()
        if bbox is None:
            print(f"  sub_{idx}: empty inner, skip"); idx += 1; continue
        full_x0 = x0 + mx + bbox[0]
        full_y0 = y0 + my + bbox[1]
        full_x1 = x0 + mx + bbox[2]
        full_y1 = y0 + my + bbox[3]
        char = img.crop((full_x0, full_y0, full_x1, full_y1))
        char.save(OUT_DIR / f"sub_{idx}.png")
        print(f"  sub_{idx}.png  {char.size[0]}×{char.size[1]}")
        idx += 1
