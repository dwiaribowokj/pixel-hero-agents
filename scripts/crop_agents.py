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

    # Margin dalam (%) untuk hilangkan fragmen tetangga di tepi cell
    MARGIN_X = 0.10   # 10% margin kiri+kanan
    MARGIN_Y = 0.12   # 12% margin atas+bawah
    mx = int(cell_w * MARGIN_X)
    my = int(cell_h * MARGIN_Y)
    print(f"Inner crop margin: {mx}px × {my}px (X:{int(MARGIN_X*100)}% Y:{int(MARGIN_Y*100)}%)")

    idx = 0
    for row in range(ROWS):
        for col in range(COLS):
            x0 = col * cell_w
            y0 = row * cell_h
            # Inner box: skip tepi cell yang mungkin berisi fragmen tetangga
            inner = img.crop((x0 + mx, y0 + my,
                              x0 + cell_w - mx, y0 + cell_h - my))
            bbox = inner.getbbox()
            if bbox is None:
                print(f"  agent_{idx}: empty inner cell, skip")
                idx += 1
                continue
            # bbox sekarang dalam koordinat inner; convert ke koordinat full image
            full_x0 = x0 + mx + bbox[0]
            full_y0 = y0 + my + bbox[1]
            full_x1 = x0 + mx + bbox[2]
            full_y1 = y0 + my + bbox[3]
            char = img.crop((full_x0, full_y0, full_x1, full_y1))
            out_path = OUT_DIR / f"agent_{idx}.png"
            char.save(out_path)
            print(f"  agent_{idx}.png  raw={cell_w}×{cell_h} "
                  f"cropped={char.size[0]}×{char.size[1]}")
            idx += 1

if __name__ == "__main__":
    main()
