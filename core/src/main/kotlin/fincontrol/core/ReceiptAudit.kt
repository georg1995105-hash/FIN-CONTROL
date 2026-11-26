package fincontrol.core

import java.math.BigDecimal
import java.math.RoundingMode

data class ReceiptLine(val quantity: BigDecimal?, val unitPrice: BigDecimal?, val printedTotal: BigDecimal?)
data class Receipt(val currency: String, val lines: List<ReceiptLine>, val separateDiscount: BigDecimal?, val printedTotal: BigDecimal?, val complete: Boolean, val confirmed: Boolean)
enum class AuditStatus { MATCH, DISCREPANCY, NEEDS_REVIEW }
data class Difference(val field: String, val printed: BigDecimal, val calculated: BigDecimal) {
    val delta: BigDecimal get() = printed.subtract(calculated)
}
data class AuditResult(val status: AuditStatus, val calculated: BigDecimal? = null, val differences: List<Difference> = emptyList(), val reason: String? = null)

/** RUB purchases only. Prices are final (tax included); discount is separate, not already applied. */
object ReceiptAudit {
    /**
     * PRELIMINARY arithmetic from source-observed values, not human-confirmed facts.
     * Only the separate preview status type may be exposed to the UI.
     */
    internal fun calculateObserved(receipt: Receipt): AuditResult {
        if (!receipt.complete || receipt.confirmed)
            return AuditResult(AuditStatus.NEEDS_REVIEW, reason = "Invalid preliminary calculation")
        return calculate(receipt)
    }
    private fun money(value: BigDecimal?): BigDecimal? = value?.takeIf { it.signum() >= 0 && it.precision() <= 18 && it.scale() in 0..2 }?.setScale(2)
    fun check(receipt: Receipt): AuditResult {
        if (!receipt.complete || !receipt.confirmed)
            return AuditResult(AuditStatus.NEEDS_REVIEW, reason = "Unconfirmed or incomplete document")
        return calculate(receipt)
    }
    private fun calculate(receipt: Receipt): AuditResult {
        fun review(reason: String) = AuditResult(AuditStatus.NEEDS_REVIEW, reason = reason)
        if (receipt.currency != "RUB") return review("Unsupported currency")
        if (receipt.lines.isEmpty() || receipt.lines.size > 10000) return review("Invalid line count")
        val discount = money(receipt.separateDiscount) ?: return review("Unknown or invalid separate discount")
        val total = money(receipt.printedTotal) ?: return review("Invalid printed total")
        val differences = mutableListOf<Difference>()
        var sum = BigDecimal.ZERO.setScale(2)
        for ((index, line) in receipt.lines.withIndex()) {
            val quantity = line.quantity?.takeIf { it.signum() > 0 && it.precision() <= 12 && it.scale() in 0..6 } ?: return review("Invalid quantity at line ${index + 1}")
            val unit = money(line.unitPrice) ?: return review("Invalid unit price at line ${index + 1}")
            val printed = money(line.printedTotal) ?: return review("Invalid line total at line ${index + 1}")
            val calculated = quantity.multiply(unit).setScale(2, RoundingMode.HALF_UP)
            if (printed != calculated) differences.add(Difference("line:${index + 1}", printed, calculated))
            sum = sum.add(calculated)
        }
        if (discount > sum) return review("Discount exceeds subtotal")
        val calculated = sum.subtract(discount)
        if (total != calculated) differences.add(Difference("total", total, calculated))
        return AuditResult(if (differences.isEmpty()) AuditStatus.MATCH else AuditStatus.DISCREPANCY, calculated, differences.toList())
    }
}
