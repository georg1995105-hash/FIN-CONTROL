package pro.veor.fincontrol

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import fincontrol.core.AuditStatus
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.IOException
import java.text.DateFormat
import java.util.Date

/** Private locally saved records, always saved only by an explicit user gesture. */
@Composable
fun AuditHistoryScreen() {
    val context = LocalContext.current.applicationContext
    val scope = rememberCoroutineScope()
    var records by remember { mutableStateOf(emptyList<SavedInvoiceAudit>()) }
    var busy by remember { mutableStateOf(true) }
    var notice by remember { mutableStateOf<String?>(null) }
    var refresh by remember { mutableIntStateOf(0) }
    var expandId by remember { mutableStateOf<Long?>(null) }
    var deletePrompt by remember { mutableStateOf<SavedInvoiceAudit?>(null) }
    var exporting by remember { mutableStateOf<SavedInvoiceAudit?>(null) }

    val saveReport = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("text/plain")
    ) { uri ->
        val item = exporting
        exporting = null
        if (uri != null && item != null) {
            scope.launch {
                try {
                    withContext(Dispatchers.IO) {
                        val stream = context.contentResolver.openOutputStream(uri, "wt")
                            ?: throw IOException("Не удалось создать файл отчёта")
                        stream.bufferedWriter(Charsets.UTF_8).use {
                            it.write(LocalAuditHistory.exportText(item))
                        }
                    }
                    notice = "Отчёт сохранён в выбранный файл."
                } catch (e: Exception) {
                    notice = "Ошибка сохранения отчёта: " + (e.localizedMessage ?: "недоступно")
                }
            }
        }
    }

    LaunchedEffect(refresh) {
        busy = true
        try {
            records = withContext(Dispatchers.IO) { LocalAuditHistory.list(context) }
        } catch (e: Exception) {
            notice = "История недоступна: " + (e.localizedMessage ?: "ошибка хранения")
        } finally { busy = false }
    }

    Text("Сохранённые проверки", style = MaterialTheme.typography.titleLarge,
        fontWeight = FontWeight.SemiBold)
    Text("Только расчёты, которые ты сам подтвердил и сохранил. Снимки не копируются в историю.",
        color = MaterialTheme.colorScheme.onSurfaceVariant)
    if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
    notice?.let {
        Text(it, color = MaterialTheme.colorScheme.onSurfaceVariant)
        TextButton(onClick = { notice = null }) { Text("Закрыть") }
    }

    if (!busy && records.isEmpty()) {
        Surface(
            color = MaterialTheme.colorScheme.surface,
            shape = RoundedCornerShape(18.dp),
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("История пока пустая", fontWeight = FontWeight.SemiBold)
                Text(
                    "Открой учебный счёт на главной, распознай, подтверди суммы и нажми «Сохранить проверку».",
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }

    records.forEach { item ->
        Surface(
            color = MaterialTheme.colorScheme.surface,
            shape = RoundedCornerShape(17.dp),
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(Modifier.padding(15.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                Text(item.title, fontWeight = FontWeight.SemiBold)
                if (item.demo) {
                    Text("Учебный пример · не для оплаты",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.labelMedium)
                }
                Text(DateFormat.getDateTimeInstance().format(Date(item.timestamp)),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text(
                    if (item.status == AuditStatus.MATCH) "Арифметика совпадает"
                    else "Возможное расхождение",
                    color = if (item.status == AuditStatus.MATCH)
                        MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
                    fontWeight = FontWeight.Medium
                )
                Text("Напечатано: " + item.printed + " ₽ · Расчёт: " + item.calculated + " ₽")
                if (expandId == item.id) {
                    Text(item.details, style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(
                        "Расхождение — не доказательство ущерба.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodySmall
                    )
                }
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    TextButton(onClick = {
                        expandId = if (expandId == item.id) null else item.id
                    }) { Text(if (expandId == item.id) "Свернуть" else "Подробнее") }
                    TextButton(onClick = {
                        exporting = item
                        saveReport.launch("fincontrol-report-" + item.id + ".txt")
                    }) { Text("Экспорт") }
                    TextButton(onClick = { deletePrompt = item }) { Text("Удалить") }
                }
            }
        }
    }

    deletePrompt?.let { item ->
        AlertDialog(
            onDismissRequest = { deletePrompt = null },
            title = { Text("Удалить проверку?") },
            text = { Text("Запись исчезнет из истории устройства. Отменить удаление нельзя.") },
            confirmButton = {
                TextButton(onClick = {
                    deletePrompt = null
                    scope.launch {
                        try {
                            withContext(Dispatchers.IO) {
                                if (!LocalAuditHistory.delete(context, item.id))
                                    throw IOException("Запись не найдена")
                            }
                            if (expandId == item.id) expandId = null
                            refresh++
                        } catch (e: Exception) {
                            notice = "Не удалось удалить запись: " +
                                (e.localizedMessage ?: "ошибка")
                        }
                    }
                }) { Text("Удалить") }
            },
            dismissButton = {
                TextButton(onClick = { deletePrompt = null }) { Text("Отмена") }
            }
        )
    }
}
