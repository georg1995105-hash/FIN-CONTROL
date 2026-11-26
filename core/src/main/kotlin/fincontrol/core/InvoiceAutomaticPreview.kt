package fincontrol.core

import java.math.BigDecimal

/**
 * Automatic PRELIMINARY arithmetic screening of OCR observations.
 * No human confirmation is invented. This never establishes a verified loss,
 * authentic document, complete charge or final financial conclusion.
 */
enum class AutoInvoiceState { POSSIBLE_MATCH, POSSIBLE_DISCREPANCY, NEEDS_RECAPTURE }

data class AutoInvoicePreview(
    val state: AutoInvoiceState,
    val captureRevision: Long,
    val printedTotal: BigDecimal? = null,
    val calculatedTotal: BigDecimal? = null,
    val differences: List<Difference> = emptyList(),
    val positions: List<InvoicePositionEvidence> = emptyList(),
    val reason: String? = null
) {
    val hasProvisionalResult: Boolean get() = state != AutoInvoiceState.NEEDS_RECAPTURE
}

/** Calculates automatically only when all key source rows are present and readable. */
object InvoiceAutomaticPreview {
    // Engine confidence is an operational gate, NOT a calibrated probability
    // of reading correctness. Results are always labelled provisional.
    private const val MIN_OCR_CONFIDENCE = 9000

    fun screen(
        lines: List<OcrSourceLine>,
        captureRevision: Long,
        pageCount: Int = 1
    ): AutoInvoicePreview {
        fun blocked(reason: String) = AutoInvoicePreview(
            AutoInvoiceState.NEEDS_RECAPTURE, captureRevision, reason = reason
        )
        val draft = InvoicePositionAudit.parse(lines, captureRevision, pageCount)
        if (!draft.readyForHumanReview)
            return blocked(draft.blockReason ?: "Нельзя разобрать документ без догадок")
        if (lines.size > 3000 || lines.map { it.sourceIndex }.distinct().size != lines.size)
            return blocked("Повреждены исходные строки OCR")

        val bySource = lines.associateBy { it.sourceIndex }
        for (row in draft.positions) {
            val original = bySource[row.sourceIndex] ?: return blocked("Исходная позиция отсутствует")
            if (original.rawText != row.sourceText || original.box != row.sourceBox)
                return blocked("Исходная позиция не совпадает с OCR")
            if (original.confidenceBasisPoints < MIN_OCR_CONFIDENCE)
                return blocked("Распознавание позиции недостаточно надёжно")
        }
        val printed = draft.printedTotal ?: return blocked("Итог не найден")
        val totalLine = bySource[draft.totalSourceIndex] ?: return blocked("Исходный итог отсутствует")
        if (totalLine.rawText != draft.totalSourceText ||
            totalLine.confidenceBasisPoints < MIN_OCR_CONFIDENCE)
            return blocked("Итог распознан недостаточно надёжно")
        if (lines.none {
                (it.rawText.trim().startsWith("СЧЁТ", true) ||
                    it.rawText.trim().startsWith("СЧЕТ", true) ||
                    it.rawText.trim().startsWith("НАКЛАДНАЯ", true) ||
                    it.rawText.trim().startsWith("СМЕТА", true)) &&
                    it.confidenceBasisPoints >= MIN_OCR_CONFIDENCE
            })
            return blocked("Заголовок документа недостаточно надёжно распознан")

        val observed = Receipt(
            currency = "RUB",
            lines = draft.positions.map {
                ReceiptLine(it.quantity, it.unitPrice, it.printedLineTotal)
            },
            separateDiscount = BigDecimal.ZERO,
            printedTotal = printed,
            complete = true, // complete within the strict parsed OCR layout only
            confirmed = false // must never claim user confirmation
        )
        val arithmetic = ReceiptAudit.calculateObserved(observed)
        return when (arithmetic.status) {
            AuditStatus.MATCH -> AutoInvoicePreview(
                AutoInvoiceState.POSSIBLE_MATCH, captureRevision,
                printedTotal = printed, calculatedTotal = arithmetic.calculated,
                positions = draft.positions.toList()
            )
            AuditStatus.DISCREPANCY -> AutoInvoicePreview(
                AutoInvoiceState.POSSIBLE_DISCREPANCY, captureRevision,
                printedTotal = printed, calculatedTotal = arithmetic.calculated,
                differences = arithmetic.differences.toList(),
                positions = draft.positions.toList()
            )
            AuditStatus.NEEDS_REVIEW -> blocked(arithmetic.reason ?: "Недостаточно данных для расчёта")
        }
    }
}
