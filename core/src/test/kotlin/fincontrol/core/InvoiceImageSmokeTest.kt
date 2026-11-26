package fincontrol.core

import java.io.File

/**
 * Reproducible Linux-Tesseract → genuine OCR words → source lines → Kotlin
 * arithmetic. The oracle confirmations below are SIMULATED from a known
 * synthetic fixture, not user confirmation or device accuracy evidence.
 */
fun main(args: Array<String>) {
    require(args.size == 1) { "Pass synthetic fixture directory" }
    val root = File(args[0])
    val expected = File(root, "expected.tsv").readLines().filter { it.isNotBlank() }
    var passed = 0
    var unsupported = 0
    var accepted = 0
    for (record in expected) {
        val fields = record.split('\t')
        require(fields.size == 2) { "Invalid fixture label" }
        val (name, truth) = fields
        val src = File(root, name + ".ocr.tsv").readLines().filter { it.isNotBlank() }.map { text ->
            val t = text.split('\t', limit = 7)
            require(t.size == 7) { "Invalid OCR row for $name" }
            OcrSourceLine(
                t[0].toInt(), t[6], OcrLineBox(
                    t[2].toInt(), t[3].toInt(), t[4].toInt(), t[5].toInt()
                ), t[1].toInt()
            )
        }
        val draft = InvoicePositionAudit.parse(src, captureRevision = 42)
        val actual = if (!draft.readyForHumanReview) AuditStatus.NEEDS_REVIEW else {
            accepted++
            val total = UserVerifiedTotal(
                draft.printedTotal!!, draft.totalSourceIndex!!,
                src.first { it.sourceIndex == draft.totalSourceIndex }.box, 42
            )
            InvoicePositionAudit.confirmAndCalculate(
                draft, draft.positions.map { it.sourceIndex }.toSet(), total, true, 42
            ).status
        }
        if (actual == AuditStatus.NEEDS_REVIEW) unsupported++
        require(actual.name == truth) {
            "$name: expected $truth, actual $actual, reason " + draft.blockReason
        }
        passed++
    }
    require(passed == 10 && accepted == 5 && unsupported == 5) {
        "Synthetic benchmark composition changed: $passed total, $accepted accepted, $unsupported rejected"
    }
    println("PASS: $passed/10 synthetic invoice OCR image outcomes; 5 support and 5 safety refusals")
    println("NOT a real-document accuracy score. Confirmations were simulated against known synthetic data.")
}
