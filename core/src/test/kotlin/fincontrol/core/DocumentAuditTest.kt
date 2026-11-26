package fincontrol.core

import java.math.BigDecimal

private fun m(s: String) = BigDecimal(s)
fun main() {
    val p = DocumentPosition("part-1", "шт", m("2"), m("100.00"))
    val q = DocumentPosition("work-1", "час", m("1"), m("500"))
    val base = ComparableDocument("RUB", listOf(p,q), true,true)
    var passed = 0
    fun test(name: String, ok: Boolean) { check(ok) { name }; passed++ }
    fun cmp(other: ComparableDocument, basis: Boolean = true) = DocumentAudit.compare(base, other, basis)
    test("same", cmp(base).status == AuditStatus.MATCH)
    test("reordered", cmp(base.copy(positions = listOf(q,p))).status == AuditStatus.MATCH)
    test("numeric scale", cmp(base.copy(positions = listOf(p.copy(price=m("100"),quantity=m("2.0")),q))).status == AuditStatus.MATCH)
    test("price", cmp(base.copy(positions=listOf(p.copy(price=m("130")),q))).changes.single().key == p.key)
    test("quantity", cmp(base.copy(positions=listOf(p.copy(quantity=m("3")),q))).status == AuditStatus.DISCREPANCY)
    test("removed", cmp(base.copy(positions=listOf(p))).changes.single().after == null)
    test("added", cmp(base.copy(positions=listOf(p,q,p.copy(key="part-2")))).changes.single().before == null)
    test("duplicate key", cmp(base.copy(positions=listOf(p,p))).status == AuditStatus.NEEDS_REVIEW)
    test("unit conflict", cmp(base.copy(positions=listOf(p.copy(unit="кг"),q))).status == AuditStatus.NEEDS_REVIEW)
    test("currency", cmp(base.copy(currency="EUR")).status == AuditStatus.NEEDS_REVIEW)
    test("unconfirmed", cmp(base.copy(confirmed=false)).status == AuditStatus.NEEDS_REVIEW)
    test("incomplete", cmp(base.copy(complete=false)).status == AuditStatus.NEEDS_REVIEW)
    test("basis", cmp(base,false).status == AuditStatus.NEEDS_REVIEW)
    test("negative", cmp(base.copy(positions=listOf(p.copy(price=m("-1")),q))).status == AuditStatus.NEEDS_REVIEW)
    test("fractional money", cmp(base.copy(positions=listOf(p.copy(price=m("1.001")),q))).status == AuditStatus.NEEDS_REVIEW)
    test("blank key", cmp(base.copy(positions=listOf(p.copy(key=" "),q))).status == AuditStatus.NEEDS_REVIEW)
    fun due(t:String?, a:String?, d:String?, c:Boolean=true)=DocumentAudit.balance(t?.let(::m),a?.let(::m),d?.let(::m),c)
    test("advance correct", due("1000","250","750").status==AuditStatus.MATCH)
    test("advance ignored", due("1000","250","1000").differences.single().delta==m("250.00"))
    test("paid in full", due("1000","1000","0").status==AuditStatus.MATCH)
    test("unknown advance", due("1000",null,"1000").status==AuditStatus.NEEDS_REVIEW)
    test("excess advance", due("1000","1200","0").status==AuditStatus.NEEDS_REVIEW)
    test("unconfirmed balance", due("1000","250","750",false).status==AuditStatus.NEEDS_REVIEW)
    test("negative due", due("1000","250","-1").status==AuditStatus.NEEDS_REVIEW)
    test("exact cents", due("1000.01","250.02","749.99").status==AuditStatus.MATCH)
    println("PASS: $passed document audit scenarios")
}
