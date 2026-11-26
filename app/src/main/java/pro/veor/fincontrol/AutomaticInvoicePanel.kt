package pro.veor.fincontrol

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import fincontrol.core.*

/**
 * Main result: fully automatic, based on actually observed OCR positions.
 * It remains preliminary; no automatic financial fact is asserted.
 */
@Composable
fun AutomaticInvoicePanel(preview: AutoInvoicePreview, isDemo: Boolean) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        color = MaterialTheme.colorScheme.surface
    ) {
        Column(
            Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            Text("Автоматическая проверка", style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold)
            if (isDemo) {
                Text("Учебный документ — суммы и названия вымышлены.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            when (preview.state) {
                AutoInvoiceState.NEEDS_RECAPTURE -> {
                    Text("Проверить документ автоматически не удалось",
                        fontWeight = FontWeight.SemiBold)
                    Text(preview.reason ?: "Недостаточно читаемых данных.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text("Попробуйте сделать более чёткий снимок документа целиком.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                AutoInvoiceState.POSSIBLE_MATCH -> {
                    Text("В распознанных строках расхождений не найдено",
                        fontWeight = FontWeight.SemiBold,
                        color = MaterialTheme.colorScheme.primary)
                    Text("По прочитанным данным: " +
                        preview.calculatedTotal!!.toPlainString() + " ₽",
                        style = MaterialTheme.typography.titleMedium)
                    Text("Проверено позиций: " + preview.positions.size)
                }
                AutoInvoiceState.POSSIBLE_DISCREPANCY -> {
                    Text("Обнаружено возможное арифметическое расхождение",
                        fontWeight = FontWeight.SemiBold,
                        color = MaterialTheme.colorScheme.error)
                    Text("Напечатано: " + preview.printedTotal!!.toPlainString() +
                        " ₽ · Расчёт: " + preview.calculatedTotal!!.toPlainString() + " ₽")
                    preview.differences.forEach { diff ->
                        val index = if (diff.field.startsWith("line:"))
                            diff.field.removePrefix("line:").toIntOrNull()?.minus(1) else null
                        val source = index?.let { preview.positions.getOrNull(it) }
                        Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                            Text(
                                if (source != null) "Позиция " + (preview.positions.indexOf(source) + 1) + ": " +
                                    source.description
                                else "Итог документа",
                                fontWeight = FontWeight.SemiBold
                            )
                            Text("В документе " + diff.printed.toPlainString() +
                                " ₽, по формуле " + diff.calculated.toPlainString() +
                                " ₽, разница " + diff.delta.abs().toPlainString() + " ₽.")
                            if (source != null) {
                                Text(source.quantity.toPlainString() + " × " +
                                    source.unitPrice.toPlainString() + " ₽",
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    style = MaterialTheme.typography.bodySmall)
                                Text("Источник OCR: " + source.sourceText,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                }
            }
            if (preview.hasProvisionalResult) {
                HorizontalDivider()
                Text(
                    "Предварительная арифметическая сверка автоматически распознанных строк. " +
                        "Ошибки OCR и обрезанные части документа возможны. Это не доказанная переплата.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}
