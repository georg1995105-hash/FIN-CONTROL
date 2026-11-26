package fincontrol.core

import java.math.BigDecimal

private fun d(s: String) = BigDecimal(s)
private fun line(q: String, p: String, total: String) = ReceiptLine(d(q), d(p), d(total))
fun main() {
    val base = Receipt("RUB", listOf(line("2", "95", "190"), line("1", "65", "65"), line("2", "350", "700"), line("1", "490", "490")), d("150"), d("1445"), true, true)
    var tests = 0
    fun test(name: String, condition: Boolean) { check(condition) { name }; tests++ }
    val mismatch = ReceiptAudit.check(base)
    test("discount ignored", mismatch.status == AuditStatus.DISCREPANCY && mismatch.calculated == d("1295.00") && mismatch.differences.single().delta == d("150.00"))
    test("correct total", ReceiptAudit.check(base.copy(printedTotal = d("1295"))).status == AuditStatus.MATCH)
    test("unconfirmed", ReceiptAudit.check(base.copy(confirmed = false)).status == AuditStatus.NEEDS_REVIEW)
    test("incomplete", ReceiptAudit.check(base.copy(complete = false)).status == AuditStatus.NEEDS_REVIEW)
    test("unknown discount", ReceiptAudit.check(base.copy(separateDiscount = null)).status == AuditStatus.NEEDS_REVIEW)
    test("unsupported currency", ReceiptAudit.check(base.copy(currency = "EUR")).status == AuditStatus.NEEDS_REVIEW)
    test("empty", ReceiptAudit.check(base.copy(lines = emptyList())).status == AuditStatus.NEEDS_REVIEW)
    test("negative discount", ReceiptAudit.check(base.copy(separateDiscount = d("-1"))).status == AuditStatus.NEEDS_REVIEW)
    test("excess discount", ReceiptAudit.check(base.copy(separateDiscount = d("1500"))).status == AuditStatus.NEEDS_REVIEW)
    test("invalid precision", ReceiptAudit.check(base.copy(printedTotal = d("1.001"))).status == AuditStatus.NEEDS_REVIEW)
    test("missing line data", ReceiptAudit.check(base.copy(lines = listOf(ReceiptLine(null, d("10"), d("10"))))).status == AuditStatus.NEEDS_REVIEW)
    test("zero quantity", ReceiptAudit.check(base.copy(lines = listOf(line("0", "10", "0")))).status == AuditStatus.NEEDS_REVIEW)
    test("negative price", ReceiptAudit.check(base.copy(lines = listOf(line("1", "-10", "-10")))).status == AuditStatus.NEEDS_REVIEW)
    val fractional = base.copy(lines = listOf(line("0.125", "10.04", "1.26")), separateDiscount = d("0"), printedTotal = d("1.26"))
    test("rounding half up", ReceiptAudit.check(fractional).status == AuditStatus.MATCH)
    val badLine = fractional.copy(lines = listOf(line("0.125", "10.04", "1.25")))
    test("line error despite correct total", ReceiptAudit.check(badLine).differences.single().field == "line:1")
    test("zero payable", ReceiptAudit.check(fractional.copy(separateDiscount = d("1.26"), printedTotal = d("0"))).status == AuditStatus.MATCH)
    test("negative discrepancy", ReceiptAudit.check(base.copy(printedTotal = d("1200"))).differences.single().delta == d("-95.00"))
    test("huge exponent", ReceiptAudit.check(base.copy(printedTotal = d("1E+100000"))).status == AuditStatus.NEEDS_REVIEW)
    println("PASS: $tests receipt audit scenarios")
}
