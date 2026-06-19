"""Crop 15 agent karakter dari sheet.png ke 15 file terpisah.
Sheet adalah 5 kolom × 3 baris. Per karakter di-tight-crop ke bounding box
non-transparent supaya ukuran uniform tanpa padding berlebih.
"""
from PIL import Image
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHEET = ROOT / "assets" / "agents" / "sheet.png"
OUT_DIR = ROOT / "assets" / "agents"

COLS = 5
ROWS = 3

def main():
    img = Image.open(SHEET).convert("RGBA")
    W, H = img.size
    cell_w = W // COLS
    cell_h = H // ROWS
    print(f"Sheet: {W}×{H}, per cell: {cell_w}×{cell_h}")

    idx = 0
    for row in range(ROWS):
        for col in range(COLS):
            x0 = col * cell_w
            y0 = row * cell_h
            cell = img.crop((x0, y0, x0 + cell_w, y0 + cell_h))
            # Tight crop ke pixel non-transparent
            bbox = cell.getbbox()
            if bbox is None:
                print(f"  agent_{idx}: empty cell, skip")
                idx += 1
                continue
            char = cell.crop(bbox)
            out_path = OUT_DIR / f"agent_{idx}.png"
            char.save(out_path)
            print(f"  agent_{idx}.png  raw={cell_w}×{cell_h} "
                  f"cropped={char.size[0]}×{char.size[1]}")
            idx += 1

if __name__ == "__main__":
    main()
