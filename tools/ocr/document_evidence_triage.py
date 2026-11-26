"""Conservative document evidence triage for observed monetary values.

No guessed digits, arithmetic, new financial approvals, or model-calibrated
probability claims. Review suggestions are NEVER confirmed document totals.
"""
from dataclasses import dataclass
from math import isfinite
import re
from typing import Optional, Tuple
from total_candidate import Line
from total_row_evidence import group_rows,select,proposals,norm_text,START,OTHER,NONFINAL
from semantic_ranker import spans
from semantic_ranker_v2 import enriched,role


@dataclass(frozen=True)
class SourceAmount:
    value: str
    line_index: int
    source_line_box: tuple
    ocr_score: float
    rank_score: float
    role: str


@dataclass(frozen=True)
class Triage:
    state: str
    reason: str
    # This value is an OCR observation, NOT a financially confirmed total.
    candidate: Optional[SourceAmount] = None
    alternatives: Tuple[SourceAmount, ...] = ()
    requires_user_confirmation: bool = True


def _options(lines,observed,scores):
    """Deduplicate by observed value while preserving original source location.

    The OCR line box is not a precise character-span box. Exclude amounts in
    text explicitly describing tax/payment/change/discount, but preserve other
    observed fields for user review.
    """
    if len(observed)!=len(scores):
        raise ValueError('score count mismatch')
    best={}
    for c,raw in zip(observed,scores):
        if not isinstance(c.line,int) or c.line<0 or c.line>=len(lines):
            raise ValueError('invalid source line')
        line=lines[c.line]
        if c.amount not in [value for _,_,value in spans(line.text)]:
            raise ValueError('candidate value not present in OCR source')
        if not isfinite(c.score) or c.score!=line.score or not 0<=c.score<=1:
            raise ValueError('invalid OCR confidence or provenance')
        try:score=float(raw)
        except (ValueError,TypeError) as exc:raise ValueError('invalid rank score') from exc
        if not isfinite(score) or not 0<=score<=1:
            raise ValueError('rank score outside [0,1]')
        if c.score<.85 or role(line)=='other':
            continue
        item=SourceAmount(c.amount,c.line,line.box,round(c.score,5),
                          round(score,5),role(line))
        previous=best.get(c.amount)
        if previous is None or (score,c.score,-c.line)>(previous.rank_score,previous.ocr_score,-previous.line_index):
            best[c.amount]=item
    return tuple(sorted(best.values(),key=lambda x:(-x.rank_score,-x.ocr_score,x.line_index,x.value)))


def triage(lines,observed,scores,max_options=3):
    """Return original strictly supported evidence, or explicit review options.

    No branch may convert a rejected or ambiguous OCR document into an
    automatically supported/confirmed financial conclusion. The state
    "supported_candidate" means evidence only and still needs independent
    financial validation.
    """
    if not isinstance(max_options,int) or not 1<=max_options<=8:
        raise ValueError('invalid review budget')
    lines,groups=group_rows(lines)
    options=_options(lines,observed,scores)
    value,reason,_=select(lines,groups,observed,scores)
    if value is not None:
        links,bad,_=proposals(lines,groups)
        if bad or any(v!=value for v,i in links.values()):
            raise RuntimeError('strict candidate conflicts with row evidence')
        linked_indices={i for v,i in links.values() if v==value}
        matching=[SourceAmount(c.amount,c.line,lines[c.line].box,round(c.score,5),
                               round(float(raw),5),role(lines[c.line]))
                  for c,raw in zip(observed,scores)
                  if c.amount==value and c.line in linked_indices
                  and c.score>=.85 and float(raw)>=.85]
        if not matching:
            raise RuntimeError('strict value lacks source provenance')
        matching.sort(key=lambda c:(-c.rank_score,-c.ocr_score,c.line_index))
        return Triage('supported_candidate',reason,matching[0],(),True)
    if not options:
        return Triage('needs_recapture',reason,None,(),True)
    presented=options[:max_options]
    conflict=reason in ('unresolved_label','conflicting_totals')
    separated=len(options)==1 or options[0].rank_score-options[1].rank_score>=.15
    if not conflict and options[0].rank_score>=.85 and separated:
        return Triage('review_suggestion',reason,options[0],presented,True)
    return Triage('ambiguous_review',reason,None,presented,True)


def confirm_user_selection(result,index,*,user_confirmed=False):
    """User must explicitly select an OCR source; no implicit approval."""
    if result.state not in ('review_suggestion','ambiguous_review'):
        raise ValueError('cannot confirm this state')
    if not user_confirmed:
        return None
    if not isinstance(index,int) or not 0<=index<len(result.alternatives):
        raise ValueError('invalid review choice')
    # Still only a user-confirmed OCR field, not a financial audit verdict.
    return result.alternatives[index]


def _distance(a,b,limit=1):
    if abs(len(a)-len(b))>limit:return limit+1
    prev=list(range(len(b)+1))
    for i,ca in enumerate(a,1):
        curr=[i]
        for j,cb in enumerate(b,1):
            curr.append(min(prev[j]+1,curr[-1]+1,prev[j-1]+(ca!=cb)))
        prev=curr
        if min(prev)>limit:return limit+1
    return prev[-1]


def near_miss_labels(lines):
    """Only diagnose possible corrupted Russian total labels, never accept.

    A fuzzy resemblance is not OCR evidence. No values are returned.
    """
    matches=0
    for line in lines:
        t=norm_text(line.text)
        if START.match(t) or OTHER.match(t) or NONFINAL.match(t):
            continue
        initial=re.findall(r'[\w]+',t)[:2]
        if any(_distance(re.sub('[^А-Я]','',word.replace('0','О')),
                         target)<=1
               for word in initial for target in ('ИТОГО','ВСЕГО')):
            matches+=1
    return matches


def self_test():
    from total_candidate import Line
    from semantic_ranker_v2 import enriched
    def l(t,x=0,y=0,w=100,c=.98):return Line(t,c,(x,y,x+w,y+20))
    good=[l('ИТОГО'),l('123,45',220),l('НДС 20,00',y=50)]
    obs=enriched(good)
    r=triage(good,obs,[.97,.1])
    assert r.state=='supported_candidate' and r.candidate.value=='123,45'
    assert r.candidate.line_index==1 and r.requires_user_confirmation
    missing=[l('ТОВАР 12,00'),l('123,45',220,y=50),l('НДС 5,00',y=100)]
    obs=enriched(missing)
    r=triage(missing,obs,[.1,.96,.3])
    assert r.state=='review_suggestion' and r.candidate.value=='123,45'
    assert r.alternatives[0].line_index==1
    assert confirm_user_selection(r,0) is None
    assert confirm_user_selection(r,0,user_confirmed=True).value=='123,45'
    equal=triage(missing,obs,[.91,.90,.2])
    assert equal.state=='ambiguous_review' and equal.candidate is None
    conflict=[l('ИТОГО 123,45'),l('ИТОГО 456,78',y=50)]
    r=triage(conflict,enriched(conflict),[.97,.12])
    assert r.state=='ambiguous_review' and r.candidate is None
    assert triage([l('НДС 123,45')],enriched([l('НДС 123,45')]),[.99]).state=='needs_recapture'
    low=[l('ИТОГО 123,45',c=.84)]
    assert triage(low,enriched(low),[.99]).state=='needs_recapture'
    assert triage([],[],[]).state=='needs_recapture'
    assert near_miss_labels([l('ИТОГ0'),l('НДС'),l('ИТОГО'),l('ТОВАР')])==1
    assert near_miss_labels([l('ИТОГО НДС'),l('ВСЕГО НДС'),l('ИТ0ГО')])==1
    from dataclasses import replace
    with_bad=[replace(enriched(good)[0],amount='999,99')]
    try:triage(good,with_bad,[.9])
    except ValueError:pass
    else:raise AssertionError('forged amount was accepted')
    try:triage(good,enriched(good),[.97])
    except ValueError:pass
    else:raise AssertionError('score mismatch accepted')
    try:confirm_user_selection(triage(good,enriched(good),[.97,.1]),0,user_confirmed=True)
    except ValueError:pass
    else:raise AssertionError('conflict review failure')
    print('PASS: strict provenance, conflict veto, nonfinal filter, review-only confirmation, fuzzy diagnostics')

if __name__=='__main__':self_test()
