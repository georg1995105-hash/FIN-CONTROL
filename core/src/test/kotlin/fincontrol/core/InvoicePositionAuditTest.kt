package fincontrol.core

import java.math.BigDecimal

/**
 * Independently specified synthetic source-text fixtures, not a measured
 * OCR-on-real-photos benchmark. Every expected answer is authored explicitly.
 */
fun main() {
    var count = 0
    fun yes(name: String, ok: Boolean) { check(ok) { "FAILED: $name" }; count++ }
    val box = OcrLineBox(10, 4, 670, 30)
    fun lines(vararg s: String) = s.mapIndexed { i, t ->
        OcrSourceLine(i, t, box.copy(top = 28*i, bottom = 28*i+26), 9800)
    }
    fun parse(vararg s: String, pages: Int = 1) = InvoicePositionAudit.parse(lines(*s), 83, pages)
    fun total(draft: InvoiceReviewDraft) =
        UserVerifiedTotal(draft.printedTotal!!, draft.totalSourceIndex!!, box, 83)
    fun check(draft: InvoiceReviewDraft, all: Boolean = true,
              confirmed: UserVerifiedTotal? = total(draft),
              complete: Boolean = true, revision: Long = 83) =
        InvoicePositionAudit.confirmAndCalculate(
            draft, if(all) draft.positions.map { it.sourceIndex }.toSet() else emptySet(),
            confirmed, complete, revision
        )

    val good = parse("СЧЁТ № 17", "1 Кабель HDMI 2 300,00 600,00",
        "2 Переходник USB 3 100,00 300,00", "ИТОГО 900,00 ₽")
    yes("ready only for review", good.readyForHumanReview)
    yes("source 1 preserved", good.positions[0].sourceIndex == 1 && good.positions[0].sourceText.contains("HDMI"))
    yes("source 2 preserved", good.positions[1].sourceIndex == 2 && good.positions[1].description == "Переходник USB")
    yes("exact quantity", good.positions[0].quantity.compareTo(BigDecimal("2")) == 0)
    yes("exact price", good.positions[0].unitPrice.toPlainString() == "300.00")
    yes("exact printed total", good.printedTotal!!.toPlainString() == "900.00")
    yes("must confirm all rows", check(good, all = false).status == AuditStatus.NEEDS_REVIEW)
    yes("must confirm completeness", check(good, complete = false).status == AuditStatus.NEEDS_REVIEW)
    yes("no stale capture", check(good, revision = 84).status == AuditStatus.NEEDS_REVIEW)
    yes("no missing total", check(good, confirmed = null).status == AuditStatus.NEEDS_REVIEW)
    yes("valid result after review", check(good).status == AuditStatus.MATCH)
    yes("exact calculated sum", check(good).calculated!!.toPlainString() == "900.00")

    val badRow = parse("СМЕТА № 4", "1 Кабель 2 300,00 650,00", "ИТОГО 650,00 ₽")
    yes("bad printed row unchanged", badRow.positions.single().printedLineTotal.toPlainString() == "650.00")
    yes("line and total differences", check(badRow).let {
        it.status == AuditStatus.DISCREPANCY &&
            it.differences.map { d -> d.field }.containsAll(listOf("line:1", "total"))
    })
    val badTotal = parse("НАКЛАДНАЯ № 5", "1 Бумага 2 200,00 400,00",
        "2 Ластик 2 25,00 50,00", "ВСЕГО 500,00 руб")
    yes("grand total difference", check(badTotal).let {
        it.status == AuditStatus.DISCREPANCY && it.differences.size == 1 &&
            it.calculated!!.toPlainString() == "450.00"
    })
    val table = parse("СЧЁТ № 6", "НАИМЕНОВАНИЕ КОЛ-ВО ЦЕНА СУММА",
        "1 Бумага А4 5 120,50 602,50", "СУММА К ОПЛАТЕ: 602,50 ₽")
    yes("table header accepted", table.readyForHumanReview && check(table).status == AuditStatus.MATCH)
    val noCharge = parse("СЧЁТ № 7", "1 Пробник 1 0,00 0,00", "ИТОГО 0,00 ₽")
    yes("zero price explicitly supported", noCharge.readyForHumanReview && check(noCharge).status == AuditStatus.MATCH)
    val price = parse("СЧЁТ № 8", "1 Реле 10 99,99 999,90", "ИТОГО 999,90 ₽")
    yes("kopeck multiplication", check(price).calculated!!.toPlainString() == "999.90")

    val forbidden = listOf(
        "missing header" to listOf("1 Кабель 1 100,00 100,00", "ИТОГО 100,00 ₽"),
        "missing currency" to listOf("СЧЁТ № 1", "1 Кабель 1 100,00 100,00", "ИТОГО 100,00"),
        "USD" to listOf("СЧЁТ № 1 USD", "1 Кабель 1 100,00 100,00", "ИТОГО 100,00 ₽"),
        "tax" to listOf("СЧЁТ № 1", "1 Кабель 1 100,00 100,00", "НДС 20,00", "ИТОГО 100,00 ₽"),
        "discount" to listOf("СЧЁТ № 1", "1 Кабель 1 100,00 100,00", "СКИДКА 10,00", "ИТОГО 90,00 ₽"),
        "advance" to listOf("СЧЁТ № 1", "1 Кабель 1 100,00 100,00", "АВАНС 50,00", "ИТОГО 50,00 ₽"),
        "unknown charge" to listOf("СЧЁТ № 1", "1 Кабель 1 100,00 100,00", "Сервис 10,00", "ИТОГО 110,00 ₽"),
        "duplicate row" to listOf("СЧЁТ № 1", "1 Кабель 1 100,00 100,00", "1 Деталь 1 10,00 10,00", "ИТОГО 110,00 ₽"),
        "row gap" to listOf("СЧЁТ № 1", "1 Кабель 1 100,00 100,00", "3 Деталь 1 10,00 10,00", "ИТОГО 110,00 ₽"),
        "split row" to listOf("СЧЁТ № 1", "1 Кабель 1 100,00", "100,00", "ИТОГО 100,00 ₽"),
        "missing total" to listOf("СЧЁТ № 1 ₽", "1 Кабель 1 100,00 100,00"),
        "duplicate total" to listOf("СЧЁТ № 1", "1 Кабель 1 100,00 100,00", "ИТОГО 100,00 ₽", "ВСЕГО 100,00 ₽"),
        "row after total" to listOf("СЧЁТ № 1", "1 Кабель 1 100,00 100,00", "ИТОГО 100,00 ₽", "2 Товар 1 200,00 200,00"),
        "corrupted OCR" to listOf("СЧЁТ № 1 ₽", "1 Кабель 1 1O0,00 100,00", "ИТОГО 100,00 ₽"),
        "delivery" to listOf("СЧЁТ № 1", "1 Кабель 1 100,00 100,00", "ДОСТАВКА 10,00", "ИТОГО 110,00 ₽"),
        "unknown intervening row" to listOf("СЧЁТ № 1", "1 Кабель 1 100,00 100,00", "Неясный текст", "ИТОГО 100,00 ₽"),
        "foreign currency" to listOf("СЧЁТ № 1", "1 Кабель 1 100,00 100,00", "ИТОГО 100,00 €"),
        "zero quantity" to listOf("СЧЁТ № 1", "1 Кабель 0 100,00 0,00", "ИТОГО 0,00 ₽")
    )
    for ((name, sample) in forbidden) {
        yes("blocked: $name", !InvoicePositionAudit.parse(lines(*sample.toTypedArray()), 83).readyForHumanReview)
    }
    yes("multi-page blocked", !parse("СЧЁТ № 1", "1 Кабель 1 100,00 100,00",
        "ИТОГО 100,00 ₽", pages = 2).readyForHumanReview)
    val low = lines("СЧЁТ № 1", "1 Кабель 1 100,00 100,00", "ИТОГО 100,00 ₽").toMutableList()
    low[1] = low[1].copy(confidenceBasisPoints = 8300)
    yes("low-confidence money blocked", !InvoicePositionAudit.parse(low, 83).readyForHumanReview)
    val duplicatedSource = lines("СЧЁТ № 1", "1 Кабель 1 100,00 100,00", "ИТОГО 100,00 ₽").toMutableList()
    duplicatedSource[1] = duplicatedSource[1].copy(sourceIndex = 0)
    yes("duplicate OCR source blocked", !InvoicePositionAudit.parse(duplicatedSource, 83).readyForHumanReview)
    yes("stale verified sum blocked", check(good, confirmed = total(good).copy(captureRevision = 84)).status == AuditStatus.NEEDS_REVIEW)
    yes("forged verified sum blocked", check(good, confirmed = total(good).copy(amount = BigDecimal("901.00"))).status == AuditStatus.NEEDS_REVIEW)
    yes("wrong total source blocked", check(good, confirmed = total(good).copy(sourceIndex = 2)).status == AuditStatus.NEEDS_REVIEW)
    println("PASS: $count independently specified invoice arithmetic and refusal cases (synthetic text)")
}
