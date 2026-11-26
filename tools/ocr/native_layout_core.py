"""Experimental native OCR hierarchy with exact token provenance.

No recognition guesses, no arithmetic inference, no financial verdict.
The repository's existing grammar and confidence gate are injected unchanged.
"""
from collections import Counter
from dataclasses import dataclass
import csv
import io
import math


@dataclass(frozen=True)
class Word:
    text: str
    score: float
    box: tuple


@dataclass(frozen=True)
class NativeTotal:
    value: str
    label: str
    row_box: tuple
    money_box: tuple
    score: float


def valid_box(word):
    x, y, X, Y = word.box
    return all(math.isfinite(v) for v in word.box) and X > x and Y > y


def native_groups(tsv, mapping):
    """Use page/block/paragraph/line IDs, not inferred vertical clustering.

    Mapping is the existing page_image scale/translation from the rectified
    coordinate system. Malformed word observations fail closed, not disappear.
    """
    scale, dx, dy = (float(mapping[0][0]), float(mapping[0][2]),
                     float(mapping[1][2]))
    expected = ((scale, 0., dx), (0., scale, dy), (0., 0., 1.))
    if (not all(math.isfinite(v) for v in (scale, dx, dy)) or scale <= 0 or
            any(not math.isclose(float(mapping[i][j]), expected[i][j],
                                 abs_tol=1e-8, rel_tol=0.)
                for i in range(3) for j in range(3))):
        raise ValueError('unsupported_mapping')
    groups = {}
    reader = csv.DictReader(io.StringIO(tsv), delimiter='\t', quoting=csv.QUOTE_NONE)
    required = {'level','page_num','block_num','par_num','line_num','word_num',
                'left','top','width','height','conf','text'}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError('invalid_tsv_header')
    seen = set()
    for row in reader:
        if row.get('level') != '5' or not (row.get('text') or '').strip():
            continue
        try:
            if None in row: raise ValueError('unexpected_tsv_columns')
            key = tuple(int(row[k]) for k in ('page_num','block_num','par_num','line_num'))
            index = int(row['word_num'])
            x, y, w, h = (float(row[k]) for k in ('left','top','width','height'))
            confidence = float(row['conf']) / 100.
            word = Word(row['text'], confidence,
                        ((x-dx)/scale,(y-dy)/scale,(x+w-dx)/scale,(y+h-dy)/scale))
            if min(*key,index) <= 0 or (key,index) in seen or not valid_box(word):
                raise ValueError('invalid_word_geometry_or_id')
            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError('invalid_confidence')
        except (ValueError,TypeError,KeyError) as exc:
            raise ValueError('invalid_word_observation') from exc
        seen.add((key,index))
        groups.setdefault(key, []).append((index,word))
    return [[word for _,word in sorted(group,key=lambda p:p[0])] for group in groups.values()]


def union(words):
    return (min(w.box[0] for w in words),min(w.box[1] for w in words),
            max(w.box[2] for w in words),max(w.box[3] for w in words))


def native_totals(groups, *, final, start, other, nonfinal, norm_text, parse, high):
    """Same lexical grammar and >=.85 confidence; independent native grouping.

    Return only observed monetary values, with the union of original word boxes
    intersecting the exact money span. A distant separate integer is never
    interpreted as a thousands group. Unresolved explicit labels veto the page.
    """
    found = []
    bad = 0
    stats = Counter()
    for words in groups:
        if not words: continue
        parts = [norm_text(w.text) for w in words]
        text = ' '.join(parts)
        if other.match(text) or nonfinal.match(text): continue
        if not start.match(text): continue
        stats['explicit_label'] += 1
        p = parse(text)
        match = final.fullmatch(text)
        if p is None or match is None:
            bad += 1; stats['grammar_reject'] += 1; continue
        if any(not valid_box(w) for w in words):
            bad += 1; stats['invalid_box'] += 1; continue
        if any(b.box[0] < a.box[0] or
               b.box[0] < a.box[2]-.15*min(a.box[3]-a.box[1],b.box[3]-b.box[1])
               for a,b in zip(words,words[1:])):
            bad += 1; stats['overlapping_or_reordered_words'] += 1; continue
        if any(min(a.box[3],b.box[3])-max(a.box[1],b.box[1]) <
               .3*min(a.box[3]-a.box[1],b.box[3]-b.box[1])
               for i,a in enumerate(words) for b in words[i+1:]):
            bad += 1; stats['separate_rows'] += 1; continue
        lo,hi = match.span(2)
        money = []
        pos = 0
        for word,part in zip(words,parts):
            if pos < hi and pos+len(part) > lo:
                money.append(word)
            pos += len(part)+1
        if not money:
            bad += 1; stats['missing_money_source'] += 1; continue
        if any(b.box[0]-a.box[2] > .75*min(a.box[3]-a.box[1],b.box[3]-b.box[1])
               for a,b in zip(money,money[1:])):
            bad += 1; stats['wide_money_gap'] += 1; continue
        if not all(high(w.score) for w in money):
            bad += 1; stats['low_money_confidence'] += 1; continue
        if not all(high(w.score) for w in words):
            bad += 1; stats['low_context_confidence'] += 1; continue
        found.append(NativeTotal(p[1],p[0],union(words),union(money),
                                 min(w.score for w in words)))
        stats['parsed_candidate'] += 1
    if bad: return [], 'unresolved_native_label', stats
    if not found: return [], 'no_native_total', stats
    if len({p.value for p in found}) != 1: return [], 'conflicting_native_totals', stats
    return found, 'native_candidate', stats
