package fincontrol.core

import java.math.BigDecimal

data class DocumentPosition(val key: String, val unit: String, val quantity: BigDecimal, val price: BigDecimal)
data class ComparableDocument(val currency: String, val positions: List<DocumentPosition>, val confirmed: Boolean, val complete: Boolean)
data class PositionChange(val key: String, val before: DocumentPosition?, val after: DocumentPosition?)
data class Comparison(val status: AuditStatus, val changes: List<PositionChange> = emptyList(), val reason: String? = null)

/** Keys and units must be explicitly matched; prices must use the same tax/discount basis. */
object DocumentAudit {
    fun compare(before: ComparableDocument, after: ComparableDocument, samePriceBasis: Boolean): Comparison {
        fun review(reason: String) = Comparison(AuditStatus.NEEDS_REVIEW, reason = reason)
        fun valid(doc: ComparableDocument): Boolean = doc.confirmed && doc.complete && doc.currency == "RUB" &&
            doc.positions.size in 1..10000 && doc.positions.all {
                it.key.isNotBlank() && it.key.length <= 256 && it.unit.isNotBlank() && it.unit.length <= 32 &&
                it.quantity.signum() > 0 && it.quantity.precision() <= 12 && it.quantity.scale() in 0..6 &&
                it.price.signum() >= 0 && it.price.precision() <= 18 && it.price.scale() in 0..2
            } && doc.positions.map { it.key }.toSet().size == doc.positions.size
        if (!samePriceBasis || !valid(before) || !valid(after)) return review("Unconfirmed, incomplete, ambiguous or unsupported document")
        val a = before.positions.associateBy { it.key }
        val b = after.positions.associateBy { it.key }
        if (a.keys.intersect(b.keys).any { a.getValue(it).unit != b.getValue(it).unit }) return review("Inconsistent units")
        val changes = (a.keys + b.keys).sorted().mapNotNull { key ->
            val old = a[key]; val new = b[key]
            if (old == null || new == null || old.quantity.compareTo(new.quantity) != 0 || old.price.compareTo(new.price) != 0)
                PositionChange(key, old, new) else null
        }
        return Comparison(if (changes.isEmpty()) AuditStatus.MATCH else AuditStatus.DISCREPANCY, changes)
    }

    /** All amounts are confirmed RUB; advance is a separate already-paid amount. No refund/credit handling. */
    fun balance(total: BigDecimal?, advance: BigDecimal?, printedDue: BigDecimal?, confirmed: Boolean): AuditResult {
        fun money(v: BigDecimal?) = v?.takeIf { it.signum() >= 0 && it.precision() <= 18 && it.scale() in 0..2 }?.setScale(2)
        fun review() = AuditResult(AuditStatus.NEEDS_REVIEW, reason = "Unknown or unsupported payment basis")
        if (!confirmed) return review()
        val t = money(total) ?: return review()
        val a = money(advance) ?: return review()
        val p = money(printedDue) ?: return review()
        if (a > t) return review()
        val due = t.subtract(a)
        return if (p == due) AuditResult(AuditStatus.MATCH, due)
        else AuditResult(AuditStatus.DISCREPANCY, due, listOf(Difference("due", p, due)))
    }
}
