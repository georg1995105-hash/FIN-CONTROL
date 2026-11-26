package fincontrol.core

fun main() {
    var count=0
    fun yes(name:String,ok:Boolean){check(ok){name};count++}
    val box=OcrLineBox(2,4,240,26)
    fun l(i:Int,s:String,conf:Int=9800)=OcrSourceLine(i,s,box,conf)
    fun scan(vararg ls:OcrSourceLine)=ReceiptOcrEvidence.build(1,ls.toList())
    val x=scan(l(0,"ХЛЕБ 75,00"),l(1,"НДС 10,00"),l(2,"ИТОГО 85,00"))
    val view=ReceiptTotalReview.prepare(x)
    yes("no autoselect",view.selectedIndex==null && !view.financialAuditPermitted)
    yes("label priority",view.choices.first().amount.toPlainString()=="85.00")
    yes("source origin",view.choices.first().sourceIndex==2 && view.choices.first().sourceLineBox==box)
    yes("exclude tax",view.choices.none{it.amount.toPlainString()=="10.00"})
    yes("explicit gesture",ReceiptTotalReview.confirm(x,0,1,false)==null)
    yes("old capture",ReceiptTotalReview.confirm(x,0,2,true)==null)
    yes("not audit",ReceiptTotalReview.confirm(x,0,1,true)!!.requiresFullDocumentAudit)
    yes("no label stays manual",ReceiptTotalReview.prepare(scan(l(0,"УСЛУГА 200,50"))).selectedIndex==null)
    yes("low confidence",ReceiptTotalReview.prepare(scan(l(0,"ИТОГО 999,99",8499))).choices.isEmpty())
    yes("no decimals",ReceiptTotalReview.prepare(scan(l(0,"ИТОГО 999"))).choices.isEmpty())
    yes("negative",ReceiptTotalReview.prepare(scan(l(0,"ИТОГО -99,00"))).choices.isEmpty())
    yes("no invented digit",ReceiptTotalReview.prepare(scan(l(0,"ИТОГО 9O,00"))).choices.isEmpty())
    yes("no payment",ReceiptTotalReview.prepare(scan(l(0,"ОПЛАТА 100,00"))).choices.isEmpty())
    yes("thousands",ReceiptTotalReview.prepare(scan(l(0,"СУММА К ОПЛАТЕ 1 234,56"))).choices.single().amount.toPlainString()=="1234.56")
    yes("same value distinct sources",ReceiptTotalReview.prepare(scan(l(0,"ТОВАР 12,00"),l(1,"ТОВАР 12,00"),l(2,"ИТОГО 24,00"))).choices.size==3)
    val many=(0..20).map{l(it,"ЦЕНА "+(it+10)+",00")}
    val bounded=ReceiptTotalReview.prepare(ReceiptOcrEvidence.build(2,many))
    yes("max eight",bounded.choices.size==8)
    yes("bottom first",bounded.choices.first().sourceIndex==20)
    yes("all excluded",scan(l(0,"НДС 15,00"),l(1,"СДАЧА 10,00")).mode==TotalReviewMode.NEEDS_RECAPTURE)
    yes("revision",ReceiptOcrEvidence.build(3,listOf(l(0,"ИТОГО 24,00"))).captureRevision==3L)
    fun reject(fn:()->Unit){try{fn();error("Accepted invalid input")}catch(_:IllegalArgumentException){count++}}
    reject{ReceiptOcrEvidence.build(0,emptyList())}
    reject{scan(l(0,"ИТОГО 12,00"),l(0,"ИТОГО 13,00"))}
    reject{scan(l(-1,"ИТОГО 12,00"))}
    reject{scan(l(0,"ИТОГО 12,00",10001))}
    reject{scan(l(0,"ИТОГО 12,00").copy(box=OcrLineBox(3,5,3,7)))}
    println("PASS: "+count+" OCR evidence scenarios")
}
