"""Adapter to the existing FIN CONTROL grammar, with unchanged cross gates."""
from native_layout_core import Word, NativeTotal, native_groups, native_totals as extract
from total_row_evidence import FINAL, START, OTHER, NONFINAL, norm_text, high, parse


def native_totals(groups):
    return extract(groups, final=FINAL, start=START, other=OTHER,
                   nonfinal=NONFINAL,norm_text=norm_text,parse=parse,high=high)


def self_test():
    from page_layout_evidence import corroborate,cross_validate,PageTotal
    from total_candidate import Line
    from semantic_ranker_v2 import enriched
    def w(t,x=0,y=0,width=100,c=.98):return Word(t,c,(x,y,x+width,y+20))
    good=[w('ИТОГО'),w('123,45',220)]
    a,reason,_=native_totals([good])
    assert reason=='native_candidate' and a[0].value=='123,45'
    assert a[0].money_box==(220,0,320,20)
    assert native_totals([good,[w('НДС',0,40),w('123,45',220,40)]])[0]==a
    assert not native_totals([good,[w('ИТОГО',0,40)]])[0]
    assert not native_totals([good,[w('ИТОГО',0,40),w('456,78',220,40)]])[0]
    assert not native_totals([[w('ИТОГО'),w('123,45',220,c=.84)]])[0]
    assert not native_totals([[w('ИТОГО',c=.84),w('123,45',220)]])[0]
    assert not native_totals([[w('ИТОГО'),w('123,45',220,40)]])[0]
    assert not native_totals([[w('ИТОГО'),w('123,45',90)]])[0]
    assert not native_totals([[w('ИТОГО'),w('123,45',220),w('456,78',400)]])[0]
    assert not native_totals([[w('ВСЕГО ТОВАРОВ'),w('123,45',220)]])[0]
    a,_,_=native_totals([[w('ИТОГО'),w('1',220,width=12),w('234,56',236)]])
    assert a[0].value=='1234,56' and a[0].money_box==(220,0,336,20)
    assert not native_totals([[w('ИТОГО'),w('1',220,width=12),w('234,56',400)]])[0]
    original=[Line('ИТОГО',.98,(0,0,100,20)),Line('1234,56',.98,(220,0,336,20))]
    obs=enriched(original)
    assert cross_validate(original,obs,[.98],a)[0]=='1234,56'
    assert cross_validate(original,obs,[.84],a)[0] is None
    assert not corroborate(a,[PageTotal('1234,56','ИТОГО',(0,50,336,70),(220,50,336,70),.98)])
    print('PASS: native adapter + existing Paddle ranking / spatial vetoes')

if __name__=='__main__':self_test()
