package fincontrol.core

fun main() {
    var checked = 0
    fun test(name: String, ok: Boolean) { check(ok) { name }; checked++ }
    fun rejects(name: String, fn: () -> Unit) {
        try { fn(); error("Expected rejection: $name") }
        catch (e: IllegalArgumentException) { checked++ }
    }
    val box = OcrLineBox(1, 4, 99, 23)
    fun line(index: Int, text: String, conf: Int = 9800) = OcrSourceLine(index, text, box, conf)
    fun opt(amount: String, source: Int, role: OcrAmountRole = OcrAmountRole.UNKNOWN) =
        ObservedTotalChoice(amount, source, 9800, role)
    val sample = TotalReviewInput(1, TotalReviewMode.REVIEW_SUGGESTION,
        listOf(line(0, "ИТОГО 1 234,56 ₽"), line(1, "НДС 234,56")),
        listOf(opt("1234,56", 0)))
    val presented = ReceiptTotalReview.prepare(sample)
    test("no default selection", presented.selectedIndex == null && !presented.financialAuditPermitted)
    test("source and amount", presented.choices.single().amount.toPlainString() == "1234.56" && presented.choices.single().sourceIndex == 0)
    test("no confirmation without gesture", ReceiptTotalReview.confirm(sample, 0, 1, false) == null)
    test("no implicit selection", ReceiptTotalReview.confirm(sample, null, 1, true) == null)
    test("stale image cannot select", ReceiptTotalReview.confirm(sample, 0, 2, true) == null)
    test("invalid index", ReceiptTotalReview.confirm(sample, 3, 1, true) == null)
    val confirmed = ReceiptTotalReview.confirm(sample, 0, 1, true)!!
    test("manual selection is still just OCR", confirmed.requiresFullDocumentAudit && confirmed.amount.toPlainString() == "1234.56")
    val ambiguous = sample.copy(mode=TotalReviewMode.AMBIGUOUS_REVIEW,
        sourceLines=sample.sourceLines + line(2, "ВСЕГО 1200,00"), choices=listOf(opt("1234,56",0),opt("1200,00",2)))
    test("ambiguous never preselect", ReceiptTotalReview.prepare(ambiguous).selectedIndex == null)
    test("user can explicitly select second", ReceiptTotalReview.confirm(ambiguous, 1, 1, true)!!.amount.toPlainString() == "1200.00")
    val recapture = TotalReviewInput(2,TotalReviewMode.NEEDS_RECAPTURE,emptyList(),emptyList())
    test("recapture has no choice", ReceiptTotalReview.prepare(recapture).choices.isEmpty())
    test("recapture cannot confirm", ReceiptTotalReview.confirm(recapture,0,2,true)==null)
    rejects("fabricated value") { ReceiptTotalReview.prepare(sample.copy(choices=listOf(opt("9999,99",0)))) }
    rejects("partial numeric match") { ReceiptTotalReview.prepare(sample.copy(sourceLines=listOf(line(0,"ИТОГО 11234,56")),choices=listOf(opt("1234,56",0)))) }
    rejects("low OCR confidence") { ReceiptTotalReview.prepare(sample.copy(sourceLines=listOf(line(0,"ИТОГО 1 234,56",8400)))) }
    rejects("tax role") { ReceiptTotalReview.prepare(sample.copy(choices=listOf(opt("234,56",1,OcrAmountRole.OTHER)))) }
    rejects("tax source with wrong role") { ReceiptTotalReview.prepare(sample.copy(choices=listOf(opt("234,56",1)))) }
    rejects("negative value") { ReceiptTotalReview.prepare(sample.copy(sourceLines=listOf(line(0,"ИТОГО -1234,56")),choices=listOf(opt("1234,56",0)))) }
    rejects("missing source") { ReceiptTotalReview.prepare(sample.copy(choices=listOf(opt("1234,56",999)))) }
    rejects("duplicate source ids") { ReceiptTotalReview.prepare(sample.copy(sourceLines=sample.sourceLines+line(0,"ИТОГО 1 234,56"))) }
    rejects("duplicate choice") { ReceiptTotalReview.prepare(ambiguous.copy(choices=listOf(opt("1234,56",0),opt("1234,56",0)))) }
    rejects("invalid box") { ReceiptTotalReview.prepare(sample.copy(sourceLines=listOf(line(0,"ИТОГО 1 234,56").copy(box=OcrLineBox(1,1,1,2))))) }
    rejects("invalid rank") { ReceiptTotalReview.prepare(sample.copy(choices=listOf(opt("1234,56",0).copy(rankBasisPoints=10001)))) }
    rejects("unsupported zero revision") { ReceiptTotalReview.prepare(sample.copy(captureRevision=0)) }
    rejects("recapture with choice") { ReceiptTotalReview.prepare(sample.copy(mode=TotalReviewMode.NEEDS_RECAPTURE)) }
    rejects("strict multiple choices") { ReceiptTotalReview.prepare(ambiguous.copy(mode=TotalReviewMode.SUPPORTED_CANDIDATE)) }
    rejects("too many OCR fields") { ReceiptTotalReview.prepare(sample.copy(choices=List(9) { opt("1234,56",it) })) }
    // Partial field confirmation must not authorize complete financial audit.
    val receipt = Receipt("RUB", listOf(ReceiptLine(null,null,null)), null, confirmed.amount, false, false)
    test("full document remains unconfirmed", ReceiptAudit.check(receipt).status == AuditStatus.NEEDS_REVIEW)
    println("PASS: $checked receipt source review contract scenarios")
}
