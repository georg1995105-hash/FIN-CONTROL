package fincontrol.core

fun main() {
    var count = 0
    fun yes(why: String, ok: Boolean) { check(ok) { why }; count++ }
    val box = OcrLineBox(10, 4, 800, 42)
    fun source(vararg texts: String, confidence: Int = 9800) =
        texts.mapIndexed { i, t -> OcrSourceLine(i, t, box, confidence) }
    fun scan(vararg texts: String, pages: Int = 1) =
        InvoiceAutomaticPreview.screen(source(*texts), 55, pages)
    val common = arrayOf(
        "СЧЁТ № 17",
        "1 Кабель HDMI 2 300,00 600,00",
        "2 Переходник USB 3 100,00 300,00",
        "ИТОГО 900,00 руб"
    )
    val valid = scan(*common)
    yes("no input", scan().state == AutoInvoiceState.NEEDS_RECAPTURE)
    yes("clear document screened without any user gestures",
        valid.state == AutoInvoiceState.POSSIBLE_MATCH)
    yes("computed exact", valid.calculatedTotal?.toPlainString() == "900.00")
    yes("printed exact", valid.printedTotal?.toPlainString() == "900.00")
    yes("provenance retained", valid.positions.size == 2 &&
        valid.positions.first().sourceText == common[1] &&
        valid.positions.first().sourceIndex == 1)
    yes("no invented discrepancy", valid.differences.isEmpty())
    yes("provisional state distinct from verified audit",
        ReceiptAudit.check(Receipt("RUB", listOf(ReceiptLine(
            java.math.BigDecimal("2"), java.math.BigDecimal("300.00"),
            java.math.BigDecimal("600.00"))), java.math.BigDecimal.ZERO,
            java.math.BigDecimal("600.00"), true, false)).status == AuditStatus.NEEDS_REVIEW)
    val rowError = scan("СЧЁТ № 18", "1 Кабель 2 300,00 650,00", "ИТОГО 650,00 руб")
    yes("row difference detected automatically",
        rowError.state == AutoInvoiceState.POSSIBLE_DISCREPANCY)
    yes("both row and total difference visible",
        rowError.differences.map { it.field } == listOf("line:1", "total"))
    yes("correct source amounts, not fixed", rowError.printedTotal?.toPlainString() == "650.00" &&
        rowError.calculatedTotal?.toPlainString() == "600.00")
    val totalError = scan("НАКЛАДНАЯ № 5",
        "1 Бумага 2 200,00 400,00", "2 Ластик 2 25,00 50,00", "ВСЕГО 500,00 руб")
    yes("only total difference", totalError.state == AutoInvoiceState.POSSIBLE_DISCREPANCY &&
        totalError.differences.map { it.field } == listOf("total"))
    yes("not a supported two-page document", scan(*common, pages = 2).state == AutoInvoiceState.NEEDS_RECAPTURE)
    yes("unsupported tax", scan("СЧЁТ № 1", "1 Кабель 1 100,00 100,00",
        "НДС 20,00", "ИТОГО 120,00 руб").state == AutoInvoiceState.NEEDS_RECAPTURE)
    yes("unsupported discount", scan("СЧЁТ № 1", "1 Кабель 1 100,00 100,00",
        "СКИДКА 10,00", "ИТОГО 90,00 руб").state == AutoInvoiceState.NEEDS_RECAPTURE)
    yes("unknown charge", scan("СЧЁТ № 1", "1 Кабель 1 100,00 100,00",
        "Сервис 10,00", "ИТОГО 110,00 руб").state == AutoInvoiceState.NEEDS_RECAPTURE)
    yes("foreign currency", scan("СЧЁТ № 1 USD", "1 Кабель 1 100,00 100,00",
        "ИТОГО 100,00 руб").state == AutoInvoiceState.NEEDS_RECAPTURE)
    yes("split unrecognized OCR row", scan("СЧЁТ № 1",
        "1 Кабель 1 100,00", "100,00", "ИТОГО 100,00 руб").state == AutoInvoiceState.NEEDS_RECAPTURE)
    yes("missing total", scan("СЧЁТ № 1", "1 Кабель 1 100,00 100,00").state == AutoInvoiceState.NEEDS_RECAPTURE)
    yes("missing currency", scan("СЧЁТ № 1", "1 Кабель 1 100,00 100,00",
        "ИТОГО 100,00").state == AutoInvoiceState.NEEDS_RECAPTURE)
    yes("wrong OCR glyph", scan("СЧЁТ № 1 руб", "1 Кабель 1 1O0,00 100,00",
        "ИТОГО 100,00 руб").state == AutoInvoiceState.NEEDS_RECAPTURE)
    yes("stale revision", InvoiceAutomaticPreview.screen(source(*common), 0).state == AutoInvoiceState.NEEDS_RECAPTURE)
    val low = source(*common).toMutableList()
    low[1] = low[1].copy(confidenceBasisPoints = 8999)
    yes("borderline OCR never becomes auto result",
        InvoiceAutomaticPreview.screen(low,55).state == AutoInvoiceState.NEEDS_RECAPTURE)
    val lowHead = source(*common).toMutableList()
    lowHead[0] = lowHead[0].copy(confidenceBasisPoints = 8999)
    yes("header OCR risk",InvoiceAutomaticPreview.screen(lowHead,55).state == AutoInvoiceState.NEEDS_RECAPTURE)
    val lowTotal = source(*common).toMutableList()
    lowTotal[3] = lowTotal[3].copy(confidenceBasisPoints = 8999)
    yes("total OCR risk",InvoiceAutomaticPreview.screen(lowTotal,55).state == AutoInvoiceState.NEEDS_RECAPTURE)
    val dup = source(*common).toMutableList()
    dup[1] = dup[1].copy(sourceIndex = 0)
    yes("duplicated provenance blocked",InvoiceAutomaticPreview.screen(dup,55).state == AutoInvoiceState.NEEDS_RECAPTURE)
    for (demo in InvoiceDemoData.all) {
        val result = InvoiceAutomaticPreview.screen(source(*demo.lines.toTypedArray()), 1)
        yes("demo automatically detected: " + demo.title,
            result.state == if (demo.expectedStatus == AuditStatus.MATCH)
                AutoInvoiceState.POSSIBLE_MATCH else AutoInvoiceState.POSSIBLE_DISCREPANCY)
        yes("demo source retained", result.positions.size == 2)
    }
    yes("no preview claim on empty OCR",!InvoiceAutomaticPreview.screen(emptyList(), 1).hasProvisionalResult)
    println("PASS: $count automatic provisional OCR arithmetic and refusal cases")
}
