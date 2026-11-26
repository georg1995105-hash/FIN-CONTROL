"""Challenge the existing OCR filter on more document layouts; synthetic only."""
import json
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from ocr_benchmark import prepare, recognize

VARIANTS = ('receipt', 'invoice', 'estimate', 'duplicate_total', 'missing_discount')


def main():
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'sample.png'
        for variant in VARIANTS:
            for i in range(4):
                expected = {'ТОВАР': f'{300+i*71},50', 'СКИДКА': '20,00', 'ИТОГО': f'{280+i*71},50'}
                image = Image.new('L', (800, 460), 255)
                draw = ImageDraw.Draw(image)
                font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 27+i*2)
                lines = [('КАССОВЫЙ ЧЕК', ''), ('Молоко 2 шт.', '100,00')]
                if variant == 'invoice':
                    lines = [('СЧЕТ НА ОПЛАТУ', ''), ('Работа', expected['ТОВАР']), ('Скидка', '20,00'), ('Всего к оплате', expected['ИТОГО'])]
                elif variant == 'estimate':
                    lines = [('СМЕТА', ''), ('Материалы', expected['ТОВАР']), ('Итого с учетом скидки', expected['ИТОГО'])]
                else:
                    lines += list(expected.items())
                    if variant == 'duplicate_total': lines.append(('ИТОГО', '999,99'))
                    if variant == 'missing_discount': lines = [x for x in lines if x[0] != 'СКИДКА']
                for j, (label, value) in enumerate(lines):
                    draw.text((35, 30+j*61), label, fill=0, font=font)
                    if value: draw.text((730, 30+j*61), value, fill=0, font=font, anchor='ra')
                image = prepare(image)
                image.save(path)
                raw, candidate, _ = recognize(path)
                rows.append({'variant':variant, 'candidate':candidate, 'unsafe':candidate and (variant!='receipt' or raw!=expected)})
    result = {'samples':len(rows), 'variants':{v:{'samples':4, 'candidates':sum(r['candidate'] for r in rows if r['variant']==v), 'unsafe':sum(r['unsafe'] for r in rows if r['variant']==v)} for v in VARIANTS}}
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
