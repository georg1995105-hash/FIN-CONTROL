package pro.veor.fincontrol

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Typeface
import fincontrol.core.DemoInvoiceCase

/** A real OCR input drawn on-device. Clearly marked as fictional. */
object DemoInvoiceFactory {
    fun create(sample: DemoInvoiceCase): LoadedDocument {
        val bitmap = Bitmap.createBitmap(1400, 1700, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        canvas.drawColor(Color.WHITE)
        val ink = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.rgb(27, 38, 45)
            typeface = Typeface.create("sans-serif", Typeface.NORMAL)
            textSize = 39f
        }
        val muted = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.rgb(100, 105, 108)
            textSize = 26f
            typeface = Typeface.create("sans-serif", Typeface.NORMAL)
        }
        val border = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.rgb(210, 214, 218)
            style = Paint.Style.STROKE
            strokeWidth = 3f
        }
        canvas.drawRoundRect(44f, 60f, 1356f, 1530f, 20f, 20f, border)
        var y = 160f
        sample.lines.forEachIndexed { index, text ->
            ink.typeface = Typeface.create("sans-serif",
                if (index == 0) Typeface.BOLD else Typeface.NORMAL)
            canvas.drawText(text, 94f, y, ink)
            y += if (index == 0) 122f else 105f
        }
        canvas.drawLine(94f, y + 10f, 1300f, y + 10f, border)
        // The notice is deliberately AFTER all source rows, never a hidden item.
        canvas.drawText("УЧЕБНЫЙ ОБРАЗЕЦ — НЕ ДЛЯ ОПЛАТЫ", 94f, 1460f, muted)
        canvas.drawText("Все названия и суммы вымышлены.", 94f, 1510f, muted)
        return LoadedDocument(bitmap, sample.title, "Пример", 1, 0, isDemo = true)
    }
}
