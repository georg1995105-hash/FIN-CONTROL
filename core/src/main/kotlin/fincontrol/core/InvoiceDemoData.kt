package fincontrol.core

/** Built-in fictional invoices, never customer documents, payments or test truth. */
data class DemoInvoiceCase(
    val title: String, val lines: List<String>, val expectedStatus: AuditStatus
)

object InvoiceDemoData {
    val correct = DemoInvoiceCase(
        "Учебный счёт — без расхождений",
        listOf(
            "СЧЁТ № 17",
            "1 Кабель HDMI 2 300,00 600,00",
            "2 Переходник USB 3 100,00 300,00",
            "ИТОГО 900,00 руб"
        ),
        AuditStatus.MATCH
    )
    val discrepancy = DemoInvoiceCase(
        "Учебный счёт — ошибка в строке",
        listOf(
            "СЧЁТ № 18",
            "1 Кабель HDMI 2 300,00 650,00",
            "2 Переходник USB 3 100,00 300,00",
            "ИТОГО 950,00 руб"
        ),
        AuditStatus.DISCREPANCY
    )
    val all get() = listOf(correct, discrepancy)
}
