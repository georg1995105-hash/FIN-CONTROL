package pro.veor.fincontrol

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.ImageDecoder
import android.graphics.pdf.PdfRenderer
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.provider.OpenableColumns
import java.io.IOException
import kotlin.math.max
import kotlin.math.roundToInt

data class LoadedDocument(
    val preview: Bitmap,
    val displayName: String,
    val kind: String,
    val pages: Int
)

/**
 * Transient offline preview. Never sends the document to a server, and never
 * pretends that preview pixels have been OCR-verified.
 */
object DocumentLoader {
    fun open(context: Context, uri: Uri): LoadedDocument {
        val mime = context.contentResolver.getType(uri) ?: ""
        val fileName = displayName(context, uri)
        return if (mime == "application/pdf" || fileName.endsWith(".pdf", ignoreCase = true)) {
            readFirstPdfPage(context, uri, fileName)
        } else {
            if (!mime.startsWith("image/") && !fileName.matches(Regex("(?i).+\\.(png|jpe?g|webp|heic|heif)"))) {
                throw IOException("Поддерживаются только фотографии и PDF.")
            }
            val source = ImageDecoder.createSource(context.contentResolver, uri)
            val bitmap = ImageDecoder.decodeBitmap(source) { decoder, info, _ ->
                val maxDimension = max(info.size.width, info.size.height)
                val divisor = max(1, (maxDimension + 1599) / 1600)
                decoder.setTargetSampleSize(divisor)
                decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
            }
            LoadedDocument(bitmap, fileName, "Фото", 1)
        }
    }

    private fun readFirstPdfPage(context: Context, uri: Uri, name: String): LoadedDocument {
        val descriptor = context.contentResolver.openFileDescriptor(uri, "r")
            ?: throw IOException("Не удалось открыть PDF.")
        descriptor.use {
            PdfRenderer(it).use { renderer ->
                if (renderer.pageCount == 0) throw IOException("PDF не содержит страниц.")
                renderer.openPage(0).use { page ->
                    val scale = minOf(1600f / max(page.width, page.height), 2f)
                    val w = max(1, (page.width * scale).roundToInt())
                    val h = max(1, (page.height * scale).roundToInt())
                    val bitmap = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
                    bitmap.eraseColor(Color.WHITE)
                    page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                    return LoadedDocument(bitmap, name, "PDF", renderer.pageCount)
                }
            }
        }
    }

    private fun displayName(context: Context, uri: Uri): String {
        var name: String? = null
        try {
            context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
                if (cursor.moveToFirst()) name = cursor.getString(0)
            }
        } catch (_: SecurityException) {
            // Content providers may not expose metadata.
        }
        return name?.take(100)?.takeIf { it.isNotBlank() } ?: "Документ"
    }
}
