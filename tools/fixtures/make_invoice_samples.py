#!/usr/bin/env python3
"""Generate synthetic Russian invoices and optionally recognize with local Tesseract.

All data are fictional. The expected outcomes are independent authored
arithmetic, not OCR machine-generated ground truth. Never use as real accuracy.
"""
import argparse
import csv
import io
import os
from collections import OrderedDict
from pathlib import Path
import subprocess
from PIL import Image, ImageDraw, ImageFont

CASES = [
 ("01_correct", ["СЧЁТ № 17", "1 Кабель 2 300,00 600,00", "2 Переходник 3 100,00 300,00", "ИТОГО 900,00 руб"], "MATCH"),
 ("02_row_error", ["СМЕТА № 4", "1 Кабель 2 300,00 650,00", "ИТОГО 650,00 руб"], "DISCREPANCY"),
 ("03_total_error", ["НАКЛАДНАЯ № 5", "1 Бумага 2 200,00 400,00", "2 Ластик 2 25,00 50,00", "ВСЕГО 500,00 руб"], "DISCREPANCY"),
 ("04_fractional", ["СЧЁТ № 6", "1 Бумага 5 120,50 602,50", "СУММА К ОПЛАТЕ: 602,50 руб"], "MATCH"),
 ("05_duplicate", ["СЧЁТ № 9", "1 Бумага 1 200,00 200,00", "1 Скрепки 2 50,00 100,00", "ИТОГО 300,00 руб"], "NEEDS_REVIEW"),
 ("06_gap", ["СЧЁТ № 10", "1 Бумага 1 200,00 200,00", "3 Скрепки 2 50,00 100,00", "ИТОГО 300,00 руб"], "NEEDS_REVIEW"),
 ("07_tax", ["СЧЁТ № 11", "1 Кабель 1 100,00 100,00", "НДС 20,00", "ИТОГО 120,00 руб"], "NEEDS_REVIEW"),
 ("08_discount", ["СЧЁТ № 12", "1 Кабель 1 100,00 100,00", "СКИДКА 10,00", "ИТОГО 90,00 руб"], "NEEDS_REVIEW"),
 ("09_unknown", ["СЧЁТ № 13", "1 Кабель 1 100,00 100,00", "Сервис 10,00", "ИТОГО 110,00 руб"], "NEEDS_REVIEW"),
 ("10_zero", ["СЧЁТ № 14", "1 Пробник 1 0,00 0,00", "ИТОГО 0,00 руб"], "MATCH")
]

def recognize(image: Path, dest: Path):
    result = subprocess.run(
        ["tesseract", str(image), "stdout", "-l", "rus", "--psm", "3", "tsv"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env=os.environ.copy()
    )
    groups = OrderedDict()
    for word in csv.DictReader(io.StringIO(result.stdout), delimiter="\t"):
        if word.get("level") != "5" or not word.get("text", "").strip() or float(word["conf"]) < 0:
            continue
        key = (word["page_num"], word["block_num"], word["par_num"], word["line_num"])
        groups.setdefault(key, []).append(word)
    rows = []
    for index, words in enumerate(groups.values()):
        confidence = round(sum(float(w["conf"]) for w in words) / len(words) * 100)
        text = " ".join(w["text"].strip() for w in words).replace("\t", " ")
        left = min(int(w["left"]) for w in words)
        top = min(int(w["top"]) for w in words)
        right = max(int(w["left"]) + int(w["width"]) for w in words)
        bottom = max(int(w["top"]) + int(w["height"]) for w in words)
        rows.append((index, confidence, left, top, right, bottom, text))
    if not rows:
        print("Diagnostic: Tesseract TSV first 1400 chars:", repr(result.stdout[:1400]))
        print("Diagnostic: Tesseract stderr:", repr(result.stderr[:1400]))
        print("Diagnostic: language root:", os.environ.get("TESSDATA_PREFIX"))
        print("Diagnostic: source image bytes:", image.stat().st_size)
        raise RuntimeError("OCR produced no recognized text lines on synthetic fixture")
    print("OCR fixture", image.name, "line count:", len(rows),
          "leading text:", [row[-1] for row in rows[:4]])
    dest.write_text("\n".join("\t".join(map(str, row)) for row in rows) + "\n", encoding="utf-8")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("outdir", type=Path)
    parser.add_argument("--ocr", action="store_true")
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    regular = ImageFont.truetype(font, 37)
    header = ImageFont.truetype(bold, 44)
    footer = ImageFont.truetype(font, 22)
    expectations = []
    for name, lines, expected in CASES:
        image = Image.new("RGB", (1400, 1700), "white")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((40, 34, 1360, 1530), radius=15, outline=(125,135,140), width=2)
        y = 125
        for index, line in enumerate(lines):
            draw.text((92, y), line, font=header if index == 0 else regular, fill=(32,39,45))
            y += 108 if index == 0 else 96
        draw.line((90, y+20, 1310, y+20), fill=(160,160,160), width=2)
        draw.text((92, 1560), "FIN CONTROL | СИНТЕТИЧЕСКИЙ ОБРАЗЕЦ | НЕ ДЛЯ ОПЛАТЫ",
                  font=footer, fill=(110,110,110))
        file = args.outdir / (name + ".png")
        image.save(file, optimize=True)
        expectations.append((name, expected))
        if args.ocr:
            recognize(file, args.outdir / (name + ".ocr.tsv"))
    (args.outdir / "expected.tsv").write_text(
        "\n".join("\t".join(row) for row in expectations) + "\n", encoding="utf-8")
    print("Generated %d fictional invoice images; all expected results are pre-authored." % len(CASES))

if __name__ == "__main__":
    main()
