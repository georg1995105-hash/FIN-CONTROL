package fincontrol.core

fun main() {
    var count = 0
    fun yes(what: String, pass: Boolean) { check(pass) { what }; count++ }
    val box = OcrLineBox(0,0,1200,100)
    for (demo in InvoiceDemoData.all) {
        val lines = demo.lines.mapIndexed { i, t ->
            OcrSourceLine(i, t, box, 9800)
        }
        val draft = InvoicePositionAudit.parse(lines, 1)
        yes("demo is visibly labelled", demo.title.contains("Учебный"))
        yes("source lines parsed", draft.readyForHumanReview)
        yes("no inferred audit without approval",
            InvoicePositionAudit.confirmAndCalculate(draft, emptySet(), null, false, 1).status == AuditStatus.NEEDS_REVIEW)
        val verified = UserVerifiedTotal(draft.printedTotal!!, draft.totalSourceIndex!!, box, 1)
        val result = InvoicePositionAudit.confirmAndCalculate(draft,
            draft.positions.map { it.sourceIndex }.toSet(), verified, true, 1)
        yes("fully confirmed arithmetic matches authored test", result.status == demo.expectedStatus)
        yes("no losses in sourced line labels", draft.positions.size == 2 &&
            draft.positions.all { it.sourceText == lines[it.sourceIndex].rawText })
        yes("wrong confirmation rejected", InvoicePositionAudit.confirmAndCalculate(
            draft, draft.positions.map { it.sourceIndex }.toSet(),
            verified.copy(amount = verified.amount.add(java.math.BigDecimal.ONE)), true, 1
        ).status == AuditStatus.NEEDS_REVIEW)
    }
    println("PASS: $count built-in demo invoice provenance and confirmation tests")
}
