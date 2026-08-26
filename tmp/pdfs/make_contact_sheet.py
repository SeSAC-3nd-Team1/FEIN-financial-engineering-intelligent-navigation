from pathlib import Path
from PIL import Image, ImageOps, ImageDraw

root = Path(__file__).resolve().parents[2]
src = root / "tmp" / "pdfs" / "rendered_opensource_formats"
files = sorted(src.glob("page-*.png"))
thumbs = []
for i, f in enumerate(files, 1):
    im = Image.open(f).convert("RGB")
    im.thumbnail((520, 370))
    card = Image.new("RGB", (540, 410), "white")
    card.paste(im, ((540-im.width)//2, 24))
    ImageDraw.Draw(card).text((10, 6), f"Page {i}", fill="black")
    thumbs.append(card)
sheet = Image.new("RGB", (540*3, 410*4), "#D8DEE6")
for i, card in enumerate(thumbs):
    sheet.paste(card, ((i%3)*540, (i//3)*410))
out = src / "contact_sheet.png"
sheet.save(out)
print(out)
