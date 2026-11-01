"""Render representative source pages for review without modifying the PDFs."""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Preview exists; choose a new output path")
    import pypdfium2 as pdfium
    from PIL import Image, ImageDraw

    sources = [next(iter(sorted(directory.glob("*.pdf")))) for directory in sorted(args.corpus.iterdir())
               if directory.is_dir() and any(directory.glob("*.pdf"))]
    if len(sources) != 6:
        parser.error("Expected six document categories")
    sheet = Image.new("RGB", (1800, 1740), "#e5e7eb")
    draw = ImageDraw.Draw(sheet)
    for index, source in enumerate(sources):
        with pdfium.PdfDocument(source) as document:
            page = document[0]
            bitmap = page.render(scale=1.5)
            image = bitmap.to_pil().convert("RGB")
            image.thumbnail((570, 815))
            x, y = (index % 3) * 600 + 15, (index // 3) * 870 + 35
            sheet.paste(image, (x, y))
            draw.text((x, y - 25), source.parent.name, fill="#111827")
            image.close()
            bitmap.close()
            page.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        sheet.save(stream, format="PNG")
    sheet.close()
    print(f"Rendered {len(sources)} source pages to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
