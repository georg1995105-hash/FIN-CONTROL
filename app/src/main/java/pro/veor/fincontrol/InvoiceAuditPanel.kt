package pro.veor.fincontrol

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import fincontrol.core.*

/**
 * Document arithmetic requires confirmation of EVERY OCR source row, its total
 * and the completeness of the captured image. This is not a universal invoice
 * parser, nor a legal/financial proof of overcharging.
 */
@Composable
fun InvoiceAuditPanel(
    reading: OcrReading,
    pageCount: Int,
    revision: Long,
    confirmedTotal: UserVerifiedTotal?,
    documentName: String,
    isDemo: Boolean
) {
    val draft = remember(reading, pageCount, revision) {
        InvoicePositionAudit.parse(reading.input.sourceLines, revision, pageCount)
    }
    var checked by remember(draft) { mutableStateOf(emptySet<Int>()) }
    var complete by remember(draft) { mutableStateOf(false) }
    var audit by remember(draft) { mutableStateOf<AuditResult?>(null) }
    var savedRecord by remember(draft) { mutableStateOf<Long?>(null) }
    var isSaving by remember(draft) { mutableStateOf(false) }
    var saveError by remember(draft) { mutableStateOf<String?>(null) }
    val context = LocalContext.current.applicationContext
    val scope = rememberCoroutineScope()
    LaunchedEffect(confirmedTotal) {
        audit = null
        savedRecord = null
        saveError = null
    }
    val totalVerified = confirmedTotal != null && draft.printedTotal != null &&
        confirmedTotal.sourceIndex == draft.totalSourceIndex &&
        confirmedTotal.captureRevision == revision &&
        confirmedTotal.amount.compareTo(draft.printedTotal) == 0

    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        color = MaterialTheme.colorScheme.surface
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text("Сверка позиций счёта", style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold)
            if (!draft.readyForHumanReview) {
                Text(
                    "Автоматическая сверка пока недоступна: " +
                        (draft.blockReason ?: "формат документа не поддержан") + ".",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Text(
                    "Поддерживается одностраничный счёт в рублях: номер, наименование, " +
                        "целое количество, цена и сумма каждой позиции, отдельная строка ИТОГО. " +
                        "Неоднозначные документы не проверяются автоматически.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            } else {
                Text(
                    "Сравните каждую строку с изображением выше. " +
                        "Не подтверждайте ошибочно распознанные цифры.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodySmall
                )
                draft.positions.forEachIndexed { index, position ->
                    Surface(color = MaterialTheme.colorScheme.surfaceVariant,
                        shape = RoundedCornerShape(12.dp)) {
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(10.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Checkbox(
                                checked = position.sourceIndex in checked,
                                onCheckedChange = { value ->
                                    checked = if (value) checked + position.sourceIndex
                                              else checked - position.sourceIndex
                                    audit = null
                                }
                            )
                            Spacer(Modifier.width(6.dp))
                            Column(Modifier.weight(1f)) {
                                Text(position.description, fontWeight = FontWeight.SemiBold)
                                Text(
                                    position.quantity.toPlainString() + " × " +
                                        position.unitPrice.toPlainString() + " ₽ = " +
                                        position.printedLineTotal.toPlainString() + " ₽",
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    style = MaterialTheme.typography.bodySmall
                                )
                                Text(
                                    "Исходная строка " + (index + 1) + ": " + position.sourceText,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    style = MaterialTheme.typography.labelSmall
                                )
                            }
                        }
                    }
                }
                Text(
                    "Напечатанный итог: " + draft.printedTotal!!.toPlainString() + " ₽",
                    fontWeight = FontWeight.SemiBold
                )
                if (!totalVerified) {
                    Text("Сначала выберите и подтвердите именно строку ИТОГО выше.",
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall)
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(
                        checked = complete,
                        onCheckedChange = { complete = it; audit = null }
                    )
                    Spacer(Modifier.width(6.dp))
                    Text(
                        "Я сверил все позиции, итог и убедился, что документ целиком в кадре",
                        style = MaterialTheme.typography.bodySmall
                    )
                }
                Button(
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                    enabled = complete && checked.size == draft.positions.size && totalVerified,
                    onClick = {
                        audit = InvoicePositionAudit.confirmAndCalculate(
                            draft, checked, confirmedTotal, complete, revision
                        )
                    }
                ) { Text("Пересчитать подтверждённые позиции") }

                audit?.let { result ->
                    HorizontalDivider(color = MaterialTheme.colorScheme.outline)
                    when(result.status) {
                        AuditStatus.MATCH -> {
                            Text(
                                "Арифметика подтверждённых строк совпадает: " +
                                    result.calculated!!.toPlainString() + " ₽",
                                color = MaterialTheme.colorScheme.primary,
                                fontWeight = FontWeight.SemiBold
                            )
                        }
                        AuditStatus.DISCREPANCY -> {
                            Text(
                                "Возможное арифметическое расхождение",
                                color = MaterialTheme.colorScheme.error,
                                fontWeight = FontWeight.SemiBold
                            )
                            result.differences.forEach { diff ->
                                Text(
                                    (if (diff.field == "total") "ИТОГО" else "Позиция " +
                                        diff.field.removePrefix("line:")) + ": напечатано " +
                                        diff.printed.toPlainString() + " ₽, вычислено " +
                                        diff.calculated.toPlainString() + " ₽.",
                                    style = MaterialTheme.typography.bodyMedium
                                )
                            }
                        }
                        AuditStatus.NEEDS_REVIEW -> {
                            Text("Проверка не завершена: " + (result.reason ?: "нужна сверка"),
                                color = MaterialTheme.colorScheme.error)
                        }
                    }
                    Text(
                        "Расчёт основан на подтверждённых OCR-строках. " +
                            "Это не доказательство переплаты и не проверка подлинности документа.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodySmall
                    )
                    if (result.status != AuditStatus.NEEDS_REVIEW) {
                        Button(
                            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                            enabled = !isSaving && savedRecord == null,
                            onClick = {
                                isSaving = true
                                saveError = null
                                scope.launch {
                                    try {
                                        val id = withContext(Dispatchers.IO) {
                                            LocalAuditHistory.saveConfirmed(
                                                context, documentName, isDemo, draft,
                                                checked.toSet(), confirmedTotal, complete, revision
                                            )
                                        }
                                        savedRecord = id
                                    } catch (e: Exception) {
                                        saveError = "Не удалось сохранить: " +
                                            (e.localizedMessage ?: "ошибка хранения")
                                    } finally { isSaving = false }
                                }
                            }
                        ) {
                            Text(if (savedRecord != null) "Сохранено в историю"
                                else if (isSaving) "Сохранение..." else "Сохранить проверку")
                        }
                        if (savedRecord != null) {
                            Text("Проверка сохранена локально. Открой раздел «История».",
                                color = MaterialTheme.colorScheme.primary,
                                style = MaterialTheme.typography.bodySmall)
                        }
                        saveError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                    }
                }
            }
        }
    }
}
