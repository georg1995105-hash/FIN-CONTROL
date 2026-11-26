package fincontrol.core

import java.math.BigDecimal

data class InvoicePositionEvidence(
    val sourceIndex: Int, val sourceText: String, val sourceBox: OcrLineBox,
    val description: String, val quantity: BigDecimal, val unitPrice: BigDecimal,
    val printedLineTotal: BigDecimal
)
data class InvoiceReviewDraft(
    val captureRevision: Long, val positions: List<InvoicePositionEvidence>,
    val printedTotal: BigDecimal?, val totalSourceIndex: Int?,
    val totalSourceText: String?, val blockReason: String?
) {
    val readyForHumanReview get() = blockReason == null && positions.isNotEmpty() && printedTotal != null
}

/** Only an unambiguous single-page RUB invoice, never arbitrary receipts.
 *  OCR evidence is not a financial finding: human review is mandatory.
 */
object InvoicePositionAudit {
    private val header = Regex("""^\s*(?:СЧ[ЕЁ]Т|НАКЛАДНАЯ|СМЕТА)(?:\b|\s|№|:)""", RegexOption.IGNORE_CASE)
    private val item = Regex("""^\s*(\d{1,3})[.)]?\s+(.{2,100}?)\s+(\d{1,5})\s+(\d{1,7}[,.]\d{2})\s+(\d{1,7}[,.]\d{2})\s*(?:₽|РУБ\.?)?\s*$""", RegexOption.IGNORE_CASE)
    private val total = Regex("""^\s*(?:ИТОГО(?:\s+К\s+ОПЛАТЕ)?|ВСЕГО(?:\s+К\s+ОПЛАТЕ)?|СУММА\s+К\s+ОПЛАТЕ)\s*[:=]?\s*(\d{1,7}[,.]\d{2})\s*(?:₽|РУБ\.?)?\s*$""", RegexOption.IGNORE_CASE)
    private val money = Regex("""(?<![\p{L}\d,.+\-])\d{1,7}[,.]\d{2}(?![\w,.])""")
    private val unsupported = Regex("""(?:\bНДС\b|\bНАЛОГ\b|\bСКИДК\p{L}*|\bАВАНС\b|\bПРЕДОПЛАТ\p{L}*|\bДОСТАВК\p{L}*|\bСДАЧА\b|\bВОЗВРАТ\b|\bКОМИССИ\p{L}*|\bСБОР\b)""", RegexOption.IGNORE_CASE)
    private val foreign = Regex("""(?:[$€£]|\bUSD\b|\bEUR\b|\bGBP\b|\bТЕНГЕ\b)""", RegexOption.IGNORE_CASE)
    private val rub = Regex("""(?:₽|(?<!\p{L})(?:РУБ\.?|RUB)(?!\p{L}))""", RegexOption.IGNORE_CASE)
    private val heading = Regex("""^\s*(?:№|НАИМЕНОВАНИЕ|КОЛ|КОЛ-ВО|ЦЕНА|СУММА|ЕД\.|ПОЗИЦИИ|ТОВАРЫ|ПРОДАВЕЦ|ПОКУПАТЕЛЬ|ДАТА)(?:\b|\s|:)""", RegexOption.IGNORE_CASE)
    private val partialRow = Regex("""^\d{1,3}[.)]?\s+\S""")
    private fun decimal(s: String) = BigDecimal(s.replace(',', '.'))
    private fun deny(revision: Long, reason: String) = InvoiceReviewDraft(revision, emptyList(), null, null, null, reason)

    fun parse(lines: List<OcrSourceLine>, captureRevision: Long, pageCount: Int = 1): InvoiceReviewDraft {
        if (captureRevision <= 0 || lines.isEmpty() || lines.size > 3000)
            return deny(captureRevision, "Нет полного распознанного документа")
        if (pageCount != 1)
            return deny(captureRevision, "Многостраничный документ: нужно проверить все страницы")
        if (lines.any { it.sourceIndex < 0 || !it.box.isValid() || it.rawText.isBlank() ||
            it.rawText.length > 2048 || it.confidenceBasisPoints !in 0..10000 } ||
            lines.map { it.sourceIndex }.distinct().size != lines.size)
            return deny(captureRevision, "Повреждены источники OCR")
        val ordered = lines.sortedBy { it.sourceIndex }
        if (ordered.none { header.containsMatchIn(it.rawText) })
            return deny(captureRevision, "Не найден заголовок счёта, накладной или сметы")
        if (ordered.none { rub.containsMatchIn(it.rawText) })
            return deny(captureRevision, "Валюта RUB не подтверждена документом")
        if (ordered.any { foreign.containsMatchIn(it.rawText) })
            return deny(captureRevision, "Иностранная или смешанная валюта")
        if (ordered.any { unsupported.containsMatchIn(it.rawText) })
            return deny(captureRevision, "Налог, скидка, доставка, аванс или иной неподдерживаемый расчёт")
        val positions = mutableListOf<InvoicePositionEvidence>()
        var grand: BigDecimal? = null
        var totalIndex: Int? = null
        var totalText: String? = null
        for (line in ordered) {
            val text = line.rawText.trim()
            val m = item.matchEntire(text)
            val t = total.matchEntire(text)
            if (m == null && t == null) {
                if (money.containsMatchIn(text))
                    return deny(captureRevision, "Неразобранная денежная строка: " + line.sourceIndex)
                if (partialRow.containsMatchIn(text))
                    return deny(captureRevision, "Нераспознанная позиция: " + line.sourceIndex)
                if (!header.containsMatchIn(text) && !heading.containsMatchIn(text) &&
                    positions.isNotEmpty() && grand == null)
                    return deny(captureRevision, "Неизвестный текст между позициями")
                continue
            }
            if (line.confidenceBasisPoints < 8500)
                return deny(captureRevision, "Низкая уверенность OCR в денежной строке")
            if (m != null) {
                if (grand != null) return deny(captureRevision, "Позиция после итога")
                if (positions.size >= 100) return deny(captureRevision, "Слишком много позиций")
                val number = m.groupValues[1].toIntOrNull() ?: return deny(captureRevision, "Неверный номер позиции")
                if (number != positions.size + 1)
                    return deny(captureRevision, "Пропущенные или повторные позиции")
                val qty = decimal(m.groupValues[3])
                val price = decimal(m.groupValues[4])
                val printed = decimal(m.groupValues[5])
                if (qty.signum() <= 0 || price.signum() < 0 || printed.signum() < 0)
                    return deny(captureRevision, "Неверные денежные данные")
                positions += InvoicePositionEvidence(line.sourceIndex, line.rawText, line.box,
                    m.groupValues[2].trim(), qty, price, printed)
            } else if (t != null) {
                if (grand != null || positions.isEmpty())
                    return deny(captureRevision, "Несколько итогов или итог без позиций")
                grand = decimal(t.groupValues[1])
                totalIndex = line.sourceIndex
                totalText = line.rawText
            }
        }
        if (positions.isEmpty() || grand == null || totalIndex == null)
            return deny(captureRevision, "Не найдены все позиции и единственный итог")
        return InvoiceReviewDraft(captureRevision, positions, grand, totalIndex, totalText, null)
    }

    /** Do not call until every source line, selected total and completeness were checked. */
    fun confirmAndCalculate(
        draft: InvoiceReviewDraft, confirmedPositions: Set<Int>,
        confirmedTotal: UserVerifiedTotal?, completeDocumentConfirmed: Boolean,
        visibleCaptureRevision: Long
    ): AuditResult {
        fun review(reason: String) = AuditResult(AuditStatus.NEEDS_REVIEW, reason = reason)
        if (!draft.readyForHumanReview) return review(draft.blockReason ?: "Неполный документ")
        if (!completeDocumentConfirmed || visibleCaptureRevision != draft.captureRevision)
            return review("Не подтверждена полнота или версия документа")
        if (confirmedPositions != draft.positions.map { it.sourceIndex }.toSet())
            return review("Не все исходные позиции подтверждены")
        if (confirmedTotal == null || confirmedTotal.captureRevision != draft.captureRevision ||
            confirmedTotal.sourceIndex != draft.totalSourceIndex ||
            confirmedTotal.amount.compareTo(draft.printedTotal) != 0)
            return review("Итог из исходного документа не подтверждён")
        return ReceiptAudit.check(Receipt(
            currency = "RUB",
            lines = draft.positions.map { ReceiptLine(it.quantity, it.unitPrice, it.printedLineTotal) },
            separateDiscount = BigDecimal.ZERO, printedTotal = draft.printedTotal,
            complete = true, confirmed = true
        ))
    }
}
