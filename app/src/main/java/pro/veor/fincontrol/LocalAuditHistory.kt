package pro.veor.fincontrol

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import fincontrol.core.*
import java.text.DateFormat
import java.util.Date

/**
 * Explicitly saved audits only. Local, transactional private SQLite.
 * Never saves photos, raw OCR drafts or uncertain financial conclusions.
 */
data class SavedInvoiceAudit(
    val id: Long, val timestamp: Long, val title: String, val status: AuditStatus,
    val printed: String, val calculated: String, val details: String, val demo: Boolean
)

object LocalAuditHistory {
    private const val TABLE = "audits"

    private class Database(context: Context) :
        SQLiteOpenHelper(context, "fincontrol_audit_history.db", null, 1) {
        override fun onCreate(db: SQLiteDatabase) {
            db.execSQL("""CREATE TABLE audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at INTEGER NOT NULL,
                title TEXT NOT NULL,
                audit_status TEXT NOT NULL CHECK(audit_status IN ('MATCH','DISCREPANCY')),
                printed TEXT NOT NULL,
                calculated TEXT NOT NULL,
                details TEXT NOT NULL,
                demo INTEGER NOT NULL CHECK(demo IN (0,1))
            )""")
            db.execSQL("CREATE INDEX audits_recent ON audits(created_at DESC, id DESC)")
        }
        override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
            // Never drop or replace user audits silently.
            throw IllegalStateException("Data migration required from version $oldVersion to $newVersion")
        }
    }

    /** Recalculates from confirmed document evidence before the transaction. */
    fun saveConfirmed(
        context: Context, title: String, demo: Boolean, draft: InvoiceReviewDraft,
        positionsConfirmed: Set<Int>, totalConfirmed: UserVerifiedTotal?,
        completeConfirmed: Boolean, revision: Long
    ): Long {
        require(title.isNotBlank() && title.length <= 100) { "Invalid document name" }
        require(draft.readyForHumanReview && draft.positions.size in 1..100)
        require(completeConfirmed && draft.captureRevision == revision)
        val audit = InvoicePositionAudit.confirmAndCalculate(
            draft, positionsConfirmed, totalConfirmed, completeConfirmed, revision
        )
        require(audit.status == AuditStatus.MATCH || audit.status == AuditStatus.DISCREPANCY) {
            "Only completed confirmed calculations may be saved"
        }
        val printed = draft.printedTotal ?: error("No printed sum")
        val calculated = audit.calculated ?: error("No calculated sum")
        require(printed.signum() >= 0 && calculated.signum() >= 0)
        val details = buildString {
            appendLine("Проверенные исходные строки:")
            draft.positions.forEachIndexed { index, item ->
                appendLine("${index + 1}. [OCR #${item.sourceIndex}] ${item.sourceText}")
                appendLine("  ${item.quantity.toPlainString()} × ${item.unitPrice.toPlainString()} ₽; в документе ${item.printedLineTotal.toPlainString()} ₽")
            }
            appendLine("[OCR #${draft.totalSourceIndex}] ${draft.totalSourceText}")
            appendLine("Напечатанный итог: ${printed.toPlainString()} ₽")
            appendLine("Расчётный итог: ${calculated.toPlainString()} ₽")
            if (audit.differences.isNotEmpty()) {
                appendLine("Возможные арифметические расхождения:")
                audit.differences.forEach { diff ->
                    appendLine("${diff.field}: напечатано ${diff.printed.toPlainString()} ₽; рассчитано ${diff.calculated.toPlainString()} ₽; разница ${diff.delta.toPlainString()} ₽")
                }
            }
        }
        require(details.length <= 260_000)
        Database(context.applicationContext).use { helper ->
            val db = helper.writableDatabase
            db.beginTransaction()
            try {
                val row = ContentValues().apply {
                    put("created_at", System.currentTimeMillis())
                    put("title", title.trim())
                    put("audit_status", audit.status.name)
                    put("printed", printed.toPlainString())
                    put("calculated", calculated.toPlainString())
                    put("details", details)
                    put("demo", if (demo) 1 else 0)
                }
                val id = db.insertOrThrow(TABLE, null, row)
                require(id > 0) { "Cannot save history" }
                db.setTransactionSuccessful()
                return id
            } finally { db.endTransaction() }
        }
    }

    fun list(context: Context): List<SavedInvoiceAudit> {
        Database(context.applicationContext).use { helper ->
            helper.readableDatabase.query(
                TABLE,
                arrayOf("id","created_at","title","audit_status","printed","calculated","details","demo"),
                null,null,null,null,"created_at DESC, id DESC","200"
            ).use { cursor ->
                val found = ArrayList<SavedInvoiceAudit>()
                while (cursor.moveToNext()) {
                    val status = AuditStatus.valueOf(cursor.getString(3))
                    require(status != AuditStatus.NEEDS_REVIEW)
                    found.add(SavedInvoiceAudit(
                        cursor.getLong(0), cursor.getLong(1), cursor.getString(2),
                        status, cursor.getString(4), cursor.getString(5),
                        cursor.getString(6), cursor.getInt(7) != 0
                    ))
                }
                return found
            }
        }
    }

    fun delete(context: Context, id: Long): Boolean {
        require(id > 0)
        Database(context.applicationContext).use { helper ->
            return helper.writableDatabase.delete(TABLE, "id=?", arrayOf(id.toString())) == 1
        }
    }

    fun exportText(item: SavedInvoiceAudit): String = buildString {
        appendLine("FIN CONTROL — отчёт о проверке подтверждённых данных")
        if (item.demo) appendLine("УЧЕБНЫЙ ПРИМЕР. НЕ ЯВЛЯЕТСЯ РЕАЛЬНЫМ ДОКУМЕНТОМ.")
        appendLine("Документ: ${item.title}")
        appendLine("Дата: ${DateFormat.getDateTimeInstance().format(Date(item.timestamp))}")
        appendLine("Результат: " + if (item.status == AuditStatus.MATCH)
            "арифметика совпадает" else "возможное арифметическое расхождение")
        appendLine(item.details)
        appendLine("Результат основан на исходных OCR-строках, подтверждённых пользователем.")
        appendLine("Не является финансовым или юридическим доказательством ущерба.")
    }
}
