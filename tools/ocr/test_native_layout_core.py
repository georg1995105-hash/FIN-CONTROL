"""Standalone tests with frozen grammar fixture from main 8f2b904.
Repository adapter tests additionally use the actual imported grammar.
"""
import argparse, concurrent.futures, json, math, re, subprocess, tempfile, unittest
from pathlib import Path
from native_layout_core import Word, native_groups, native_totals
LABEL=r'(?:ИТОГО К ОПЛАТЕ|ВСЕГО К ОПЛАТЕ|СУММА К ОПЛАТЕ|ИТОГОВАЯ СУММА|ОБЩАЯ СУММА|К ОПЛАТЕ|ИТОГО|ИТОГ|ВСЕГО)'
MONEY=r'(?:[0-9]{1,3}(?: [0-9]{3}){1,2}|[0-9]{1,7})[,.][0-9]{2}'
FINAL=re.compile(r'^('+LABEL+r')\s*(?::\s*)?(?:[=*]\s*)?('+MONEY+r')\s*(?:₽|РУБ\.?|Р\.)?$')
START=re.compile(r'^'+LABEL+r'(?=$|[\s:=*0-9])')
NONFINAL=re.compile(r'^(?:НДС|НАЛОГ|СКИДКА|СДАЧА|ВОЗВРАТ|ОПЛАТА|НАЛИЧНЫМИ|БЕЗНАЛИЧНЫМИ|ПОДЫТОГ|ПРЕДОПЛАТА|ПОЛУЧЕНО|ЦЕНА|КОЛИЧЕСТВО)(?:$|[\s:=*0-9])')
OTHER=re.compile(r'^(?:(?:ИТОГО|ВСЕГО|ИТОГ)\s+(?:НДС|НАЛОГ|ПОЗИЦИЙ|ТОВАРОВ|СКИДОК|СКИДКА|БЕЗ|С НДС|НАЛИЧНЫМИ|БЕЗНАЛИЧНЫМИ)|(?:НДС|НАЛОГ|СКИДКА|СДАЧА|НАЛИЧНЫМИ|БЕЗНАЛИЧНЫМИ|ОПЛАТА|ПОЛУЧЕНО|ПОДЫТОГ|ПРЕДОПЛАТА)(?:\b|:))')
CHARS=str.maketrans('ABCEHKMOPTXY','АВСЕНКМОРТХУ')
def norm(s):return ' '.join(s.upper().replace('Ё','Е').split()).translate(CHARS)
def parse(s):
    s=norm(s)
    if OTHER.match(s) or NONFINAL.match(s):return None
    m=FINAL.fullmatch(s)
    return (m.group(1),m.group(2).replace(' ','').replace('.',',')) if m else None
def extract(groups):
    return native_totals(groups,final=FINAL,start=START,other=OTHER,nonfinal=NONFINAL,norm_text=norm,parse=parse,high=lambda s:math.isfinite(s) and .85<=s<=1.)
def w(t,x=0,y=0,width=100,c=.98):return Word(t,c,(x,y,x+width,y+20))
IDENTITY=((1,0,0),(0,1,0),(0,0,1))
HEADER='level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n'
def tsv(*rows):return HEADER+'\n'.join('\t'.join(map(str,row)) for row in rows)+'\n'
def row(text,word=1,block=1,line=1,x=22,y=42,width=60,conf=97):return (5,1,block,1,line,word,x,y,width,20,conf,text)
class NativeTests(unittest.TestCase):
    def test_explicit_and_location(self):
        a,reason,_=extract([[w('ИТОГО'),w('123,45',220)]])
        self.assertEqual(reason,'native_candidate');self.assertEqual(a[0].value,'123,45');self.assertEqual(a[0].money_box,(220,0,320,20))
    def test_conflicting_total(self):self.assertFalse(extract([[w('ИТОГО 123,45')],[w('ИТОГО 456,78',y=40)]])[0])
    def test_unresolved_label_veto(self):self.assertFalse(extract([[w('ИТОГО 123,45')],[w('ИТОГО',y=40)]])[0])
    def test_nonfinal_does_not_replace_total(self):self.assertEqual(extract([[w('ИТОГО 123,45')],[w('НДС 456,78',y=40)]])[0][0].value,'123,45')
    def test_split_thousands(self):
        a,_,_=extract([[w('ИТОГО'),w('1',220,width=12),w('234,56',236)]])
        self.assertEqual(a[0].value,'1234,56');self.assertEqual(a[0].money_box,(220,0,336,20))
    def test_distant_numbers(self):
        a,_,s=extract([[w('ИТОГО'),w('1',220,width=12),w('234,56',400)]]);self.assertFalse(a);self.assertEqual(s['wide_money_gap'],1)
    def test_context_confidence(self):
        a,_,s=extract([[w('ИТОГО',c=.84),w('123,45',220)]]);self.assertFalse(a);self.assertEqual(s['low_context_confidence'],1)
    def test_money_confidence(self):
        a,_,s=extract([[w('ИТОГО'),w('123,45',220,c=.84)]]);self.assertFalse(a);self.assertEqual(s['low_money_confidence'],1)
    def test_separate_rows(self):self.assertFalse(extract([[w('ИТОГО'),w('123,45',220,40)]])[0])
    def test_overlap(self):self.assertFalse(extract([[w('ИТОГО'),w('123,45',90)]])[0])
    def test_reordered_native_words(self):self.assertFalse(extract([[w('ИТОГО',220),w('123,45')]])[0])
    def test_two_amounts(self):self.assertFalse(extract([[w('ИТОГО'),w('123,45',220),w('456,78',400)]])[0])
    def test_unsupported_money(self):
        for text in ('ИТОГО -123,45','ИТОГО 12O,45','ИТОГО 123,4','ИТОГО 123,45 USD','ВСЕГО ТОВАРОВ 123,45','НДС 123,45'):
            with self.subTest(text=text):self.assertFalse(extract([[w(text)]])[0])
    def test_native_block_ids_and_transform(self):
        groups=native_groups(tsv(row('ИТОГО'),row('123,45',word=2,x=102),row('НДС',block=2)),((2,0,2),(0,2,2),(0,0,1)))
        self.assertEqual(len(groups),2);self.assertEqual(groups[0][0].box,(10,20,40,30));self.assertEqual(extract(groups)[0][0].value,'123,45')
    def test_duplicate_word_id(self):
        with self.assertRaises(ValueError):native_groups(tsv(row('ИТОГО'),row('123,45')),IDENTITY)
    def test_malformed_geometry(self):
        with self.assertRaises(ValueError):native_groups(tsv(row('ИТОГО',width=0)),IDENTITY)
    def test_malformed_confidence(self):
        with self.assertRaises(ValueError):native_groups(tsv(row('ИТОГО',conf='nan')),IDENTITY)
    def test_wrong_mapping(self):
        with self.assertRaises(ValueError):native_groups(tsv(row('ИТОГО')),((1,1,0),(0,1,0),(0,0,1)))
    def test_malformed_header(self):
        with self.assertRaises(ValueError):native_groups('text\nИТОГО',IDENTITY)
def smoke_ocr(output):
    from PIL import Image,ImageDraw,ImageFont
    cases=[('clean',['ИТОГО: 123,45'],'123,45'),('rubles',['ИТОГО 456,78 РУБ.'],'456,78'),('thousands',['ИТОГО 1 234,56'],'1234,56'),('label',['СУММА К ОПЛАТЕ 678,90'],'678,90'),('tax',['ИТОГО 543,21','НДС 12,34'],'543,21'),('conflict',['ИТОГО 123,45','ИТОГО 456,78'],None),('tax_only',['НДС 123,45'],None),('items',['ВСЕГО ТОВАРОВ 123,45'],None),('two_amounts',['ИТОГО 123,45 678,90'],None),('missing',['ИТОГО'],None),('split',['ИТОГО','123,45'],None)]
    with tempfile.TemporaryDirectory() as tmp:
        tasks=[]
        for name,lines,expected in cases:
            im=Image.new('L',(1000,360),255);d=ImageDraw.Draw(im);f=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',40)
            d.text((24,20),'КАССОВЫЙ ЧЕК',font=f,fill=0);d.text((24,78),'ТОВАР 1',font=f,fill=0)
            for i,line in enumerate(lines):d.text((24,150+60*i),line,font=f,fill=0)
            path=Path(tmp)/f'{name}.png';im.save(path)
            for mode in (3,4,6):tasks.append((mode,path,expected))
        def process(task):
            mode,path,expected=task
            p=subprocess.run(['tesseract',str(path),'stdout','-l','rus','--oem','1','--psm',str(mode),'tsv'],capture_output=True,text=True,timeout=25,check=True)
            totals,reason,_=extract(native_groups(p.stdout,IDENTITY));return mode,expected,totals[0].value if totals else None,reason
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(process,tasks))
    report={'scope':'synthetic rendered receipts, actual local Tesseract rus; native grammar only, no Paddle ranking','images':len(cases),'by_psm':{},'tesseract':subprocess.check_output(['tesseract','--version'],text=True).splitlines()[0]}
    for mode in (3,4,6):
        rows=[r for r in results if r[0]==mode]
        report['by_psm'][str(mode)]={'correct':sum(e is not None and v==e for _,e,v,_ in rows),'wrong':sum(v is not None and v!=e for _,e,v,_ in rows),'refused':sum(e is not None and v is None for _,e,v,_ in rows),'negative_rejected':sum(e is None and v is None for _,e,v,_ in rows),'n':len(rows)}
    Path(output).write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n');print(json.dumps(report,indent=2,ensure_ascii=False))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--ocr-report');args=parser.parse_args()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NativeTests))
    if not result.wasSuccessful():raise SystemExit(1)
    if args.ocr_report:smoke_ocr(args.ocr_report)
