"""Aggregate-only receipt layout diagnostics and conservative anchor extraction.
Expected amount is used exclusively in evaluation. No receipt text, amounts,
individual coordinates, image hashes or images are printed or persisted.
"""
import math
import re
from collections import Counter
from document_structure import (LABEL, LABEL_PREFIX, LABEL_CHARS, MONEY, OTHER,
                                FINAL, rows, row_text, valid_box, analyze, same_row)
from total_candidate import Line, good, cleaned
from ocr_preprocess import normalize

# Boundaries prevent selecting a fragment of a longer number.
TOKEN = re.compile(r'(?<![0-9,.])('+MONEY+r')(?![0-9,.])')
AMOUNT_ONLY = re.compile(r'^(?:=\s*)?('+MONEY+r')\s*(?:₽|РУБ\.?|Р\.)?$')
LABEL_ONLY = re.compile(r'^'+LABEL+r'\s*[:=]?$')
COMBINED = re.compile(r'^'+LABEL+r'\s*(?:[:=]\s*)?('+MONEY+r')\s*(?:₽|РУБ\.?|Р\.)?$')

def label_text(text):
    return cleaned(text).translate(LABEL_CHARS)

def amounts(text):
    return [normalize(m.group(1)) for m in TOKEN.finditer(cleaned(text))]

def amount_only(text):
    m=AMOUNT_ONLY.fullmatch(cleaned(text))
    return normalize(m.group(1)) if m else None

def geometry(a,b):
    """Return normalized horizontal gap and baseline displacement."""
    x,y,X,Y=a.box; u,v,U,V=b.box
    h=max(Y-y,V-v)
    return (u-X)/h,((v+V)-(y+Y))/(2*h)

def anchors(lines):
    # Include incomplete and low-confidence labels so that ambiguity is visible.
    return [l for l in lines if valid_box(l) and LABEL_PREFIX.match(label_text(l.text))
            and not OTHER.match(label_text(l.text))]

def anchor_candidate(lines):
    """Only explicit, high-confidence anchor and amount. No ranking by value.
    This alternative is exploratory, never a confirmed financial result.
    """
    lines=[l for l in lines if valid_box(l) and l.text.strip()]
    aa=anchors(lines)
    if len(aa)!=1:return None
    a=aa[0]
    if not good(a):return None
    label=label_text(a.text)
    # A combined label and number is itself sufficient only if the row has
    # no competing money. A separate amount requires alignment and clear space.
    combined=COMBINED.fullmatch(label)
    others=[l for l in lines if l is not a and same_row(a,l)]
    if combined:
        if any(amounts(l.text) for l in others):return None
        return normalize(combined.group(1))
    if not LABEL_ONLY.fullmatch(label):return None
    near=[l for l in lines if l is not a and geometry(a,l)[0]>=-.15
          and abs(geometry(a,l)[1])<=.60]
    # Reject any additional token near the anchor, including partial numbers.
    money=[l for l in near if amount_only(l.text) is not None]
    if len(money)!=1:return None
    b=money[0]
    if not good(b):return None
    if any(l is not b and amounts(l.text) for l in near):return None
    if any(l is not b and l.box[0]<b.box[2] and l.box[2]>a.box[2] for l in near):return None
    # A second explicit total hidden in a grouped row is still ambiguity.
    if analyze(lines).reason=='multiple_total_labels':return None
    return amount_only(b.text)

def diagnose(lines,expected):
    """Multi-label counters per document, plus mutually exclusive cause."""
    facts=set()
    aa=anchors(lines)
    groups=rows(lines)
    if aa:facts.add('explicit_anchor_fragment')
    if len(aa)>1:facts.add('multiple_anchor_fragments')
    matches=[l for l in lines if valid_box(l) and expected is not None and expected in amounts(l.text)]
    if matches:facts.add('reference_amount_present')
    if any(good(l) for l in matches):facts.add('reference_amount_high_confidence')
    if len(matches)>1:facts.add('reference_amount_repeated')
    total_groups=[]
    for g in groups:
        raw=' '.join(label_text(l.text) for l in g)
        if not LABEL_PREFIX.match(raw) or OTHER.match(raw):continue
        total_groups.append(g)
        if len(g)>1:facts.add('total_row_split')
        if row_text(g) is None:facts.add('total_row_geometry_rejected')
        if any(not good(l) for l in g):facts.add('total_row_low_confidence')
        if any(l is m for l in g for m in matches):facts.add('reference_in_total_row')
        if any(amounts(l.text) for l in g):facts.add('money_token_in_total_row')
        if FINAL.fullmatch(raw):facts.add('total_row_strict_syntax')
        elif amounts(raw):facts.add('total_row_money_but_nonstandard_syntax')
        elif not amounts(raw):facts.add('total_row_no_money_token')
    for a in aa:
        if not good(a):facts.add('anchor_low_confidence')
        if LABEL_ONLY.fullmatch(label_text(a.text)):facts.add('label_without_amount')
        if expected in amounts(a.text):facts.add('reference_in_anchor')
        for m in matches:
            if m is a:continue
            dx,dy=geometry(a,m)
            if dx>=-.15 and abs(dy)<=.60:
                facts.add('reference_near_right')
                if good(a) and good(m):facts.add('reference_near_right_high_confidence')
            if 0.60<dy<=3.0 and m.box[2]>=a.box[0]:
                facts.add('reference_below_anchor')
    old=analyze(lines)
    if old.amount is not None:cause='accepted'
    elif not total_groups:cause='no_grouped_label'
    elif len(total_groups)>1:cause='multiple_grouped_labels'
    elif 'total_row_geometry_rejected' in facts:cause='geometry_rejected'
    elif 'total_row_strict_syntax' in facts and 'total_row_low_confidence' in facts:cause='confidence_rejected'
    elif 'total_row_money_but_nonstandard_syntax' in facts:cause='nonstandard_syntax'
    elif 'reference_near_right' in facts:cause='row_association'
    elif 'reference_below_anchor' in facts:cause='vertical_association'
    elif 'total_row_no_money_token' in facts:cause='no_money_token'
    else:cause='other'
    return cause,sorted(facts)

def self_test():
    def l(s,x=0,y=0,w=100,h=20,c=.99):return Line(s,c,(x,y,x+w,y+h))
    tests=[
        ([l('ИТОГО 123,45')],'123,45'),
        ([l('ИТОГО'),l('=123,45',200)],'123,45'),
        ([l('ИТОГО'),l('123,45 РУБ.',200)],'123,45'),
        ([l('ИТОГО'),l('123,45',200,40)],None),
        ([l('ИТОГО'),l('123,45',200),l('234,56',400)],None),
        ([l('ИТОГО'),l('НДС',120,w=60),l('123,45',200)],None),
        ([l('ИТОГО 123,45'),l('ИТОГО 123,45',0,40)],None),
        ([l('ИТОГО 123,45'),l('999,99',200)],None),
        ([l('ИТОГО'),l('123,45',200,c=.84)],None),
        ([l('ИТОГО 123,45',c=.84)],None),
        ([l('ИТОГО НДС 123,45')],None),
        ([l('ОПЛАТА КАРТОЙ 123,45')],None),
        ([l('ИТОГО'),l('1O3,45',200)],None),
        ([l('ИТОГО'),l('123,45',200),l('СКИДКА',0,40)],'123,45'),
    ]
    for i,(lines,expected) in enumerate(tests):
        assert anchor_candidate(lines)==expected,f'anchor case {i+1}'
    cause,facts=diagnose([l('ИТОГО'),l('123,45',200,40)],'123,45')
    assert cause=='vertical_association' and 'reference_below_anchor' in facts
    cause,facts=diagnose([l('ИТОГО'),l('123,45',200,c=.84)],'123,45')
    assert cause=='confidence_rejected' and 'total_row_low_confidence' in facts
    assert amounts('1234,567')==[] and amounts('123,45')==['123,45']
    print('PASS: 14 anchor scenarios and 3 diagnostic assertions')
if __name__=='__main__':self_test()
