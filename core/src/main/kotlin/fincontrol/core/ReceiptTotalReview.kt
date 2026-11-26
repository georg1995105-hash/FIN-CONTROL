package fincontrol.core

import java.math.BigDecimal
import java.util.Locale

/** Geometry is the ORIGINAL OCR line, not a fictional per-character bound. */
data class OcrLineBox(val left: Int, val top: Int, val right: Int, val bottom: Int) {
    fun isValid(): Boolean = left >= 0 && top >= 0 && right > left && bottom > top
}

enum class OcrAmountRole { TOTAL, UNKNOWN, OTHER }
enum class TotalReviewMode { SUPPORTED_CANDIDATE, REVIEW_SUGGESTION, AMBIGUOUS_REVIEW, NEEDS_RECAPTURE }

data class OcrSourceLine(
    val sourceIndex: Int,
    val rawText: String,
    val box: OcrLineBox,
    val confidenceBasisPoints: Int
)

data class ObservedTotalChoice(
    /** Canonical OCR observation, e.g. "1234,56"; NEVER an inferred number. */
    val observedAmount: String,
    val sourceIndex: Int,
    val rankBasisPoints: Int,
    val role: OcrAmountRole
)

data class TotalReviewInput(
    val captureRevision: Long,
    val mode: TotalReviewMode,
    val sourceLines: List<OcrSourceLine>,
    val choices: List<ObservedTotalChoice>
)

data class DisplayedTotalChoice(
    val sourceIndex: Int,
    val amount: BigDecimal,
    val sourceLineText: String,
    val sourceLineBox: OcrLineBox
)

data class TotalReviewPresentation(
    val mode: TotalReviewMode,
    val captureRevision: Long,
    val choices: List<DisplayedTotalChoice>,
    val selectedIndex: Int? = null,
    val financialAuditPermitted: Boolean = false
)

/** A user-verified OCR field is NOT a verified document or financial conclusion. */
data class UserVerifiedTotal(
    val amount: BigDecimal,
    val sourceIndex: Int,
    val sourceLineBox: OcrLineBox,
    val captureRevision: Long,
    val requiresFullDocumentAudit: Boolean = true
)

object ReceiptTotalReview {
    private val canonical = Regex("""\d{1,7}[,.]\d{2}""")
    private val observedToken = Regex("""(?<![\p{L}\d,.+\-])(?:\d{1,3}(?:[ \u00a0]\d{3}){1,2}|\d{1,7})[,.]\d{2}(?![\w,.])""")
    private val excluded = Regex("""^(?:(?:ИТОГО|ВСЕГО)\s+(?:НДС|НАЛОГ|СКИДКИ|ТОВАРОВ|ПОЗИЦИЙ)|НДС|НАЛОГ|СКИДКА|СДАЧА|ВОЗВРАТ|ОПЛАТА|НАЛИЧНЫМИ|БЕЗНАЛИЧНЫМИ|ПОЛУЧЕНО|ПОДЫТОГ|ПРЕДОПЛАТА)(?:\b|\s|:)""")

    private fun normalized(token: String): String = token.replace("\u00a0", "").replace(" ", "").replace('.', ',')

    /** Validate every field before UI construction. Never preselect the highest ranked guess. */
    fun prepare(input: TotalReviewInput): TotalReviewPresentation {
        require(input.captureRevision > 0) { "Missing capture revision" }
        require(input.sourceLines.size <= 3000 && input.choices.size <= 8) { "Unsupported document size" }
        require(input.sourceLines.map { it.sourceIndex }.distinct().size == input.sourceLines.size) { "Duplicate OCR source id" }
        val sources = input.sourceLines.associateBy { it.sourceIndex }
        for (line in input.sourceLines) {
            require(line.sourceIndex >= 0 && line.box.isValid() && line.rawText.isNotBlank() && line.rawText.length <= 2048) { "Invalid OCR source" }
            require(line.confidenceBasisPoints in 0..10000) { "Invalid OCR confidence" }
        }
        if (input.mode == TotalReviewMode.NEEDS_RECAPTURE) {
            require(input.choices.isEmpty()) { "Recapture cannot contain choices" }
        } else {
            require(input.choices.isNotEmpty()) { "No source choices" }
        }
        if (input.mode == TotalReviewMode.SUPPORTED_CANDIDATE) {
            require(input.choices.size == 1) { "Strict mode needs one resolved source" }
        }
        val seen = mutableSetOf<Pair<Int, String>>()
        val choices = input.choices.map { choice ->
            require(choice.rankBasisPoints in 0..10000 && canonical.matches(choice.observedAmount)) { "Invalid observed amount or rank" }
            require(choice.role != OcrAmountRole.OTHER) { "Nonfinal amount is not a total choice" }
            require(seen.add(choice.sourceIndex to choice.observedAmount)) { "Duplicate source choice" }
            val line = sources[choice.sourceIndex] ?: throw IllegalArgumentException("Unknown OCR source")
            require(line.confidenceBasisPoints >= 8500) { "Uncertain source OCR; recapture required" }
            require(!excluded.containsMatchIn(line.rawText.trim().uppercase(Locale.ROOT))) { "Tax/payment amount cannot be offered as a total" }
            val found = observedToken.findAll(line.rawText).any { normalized(it.value) == choice.observedAmount.replace('.', ',') }
            require(found) { "Chosen amount was not read in original OCR line" }
            DisplayedTotalChoice(choice.sourceIndex, BigDecimal(choice.observedAmount.replace(',', '.')),
                line.rawText, line.box)
        }
        return TotalReviewPresentation(input.mode, input.captureRevision, choices)
    }

    /** Explicit gesture and same-image revision are mandatory; no implicit selection. */
    fun confirm(
        input: TotalReviewInput,
        selectionIndex: Int?,
        visibleCaptureRevision: Long,
        explicitlyConfirmed: Boolean
    ): UserVerifiedTotal? {
        if (!explicitlyConfirmed || selectionIndex == null || visibleCaptureRevision != input.captureRevision) return null
        val page = prepare(input)
        if (selectionIndex !in page.choices.indices) return null
        val choice = page.choices[selectionIndex]
        return UserVerifiedTotal(choice.amount, choice.sourceIndex, choice.sourceLineBox, page.captureRevision)
    }
}
