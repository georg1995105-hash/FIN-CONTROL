package pro.veor.fincontrol

import android.content.Context
import android.graphics.Bitmap
import com.googlecode.tesseract.android.PageIteratorLevel
import com.googlecode.tesseract.android.TessBaseAPI
import fincontrol.core.*
import java.io.File
import java.io.IOException
import java.security.MessageDigest
import kotlin.math.roundToInt
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

data class OcrReading(val input:TotalReviewInput,val presentation:TotalReviewPresentation,val lines:Int)

/** Fully local, SHA-512 verified, no runtime downloads; one native instance at a time. */
object OfflineRussianOcr {
    private const val MODEL="rus.traineddata"
    private const val BYTES=3861738L
    private const val SHA512="65254c36df8274cee0a2c32e9632f3c2c0032314bf0a99a4c23309e862da7c038ed85745d58697a814f44c656f22ef5a7815ae2bec33f80de1de8e1ea9dd"
    private val gate=Mutex()

    suspend fun recognize(context:Context,bitmap:Bitmap,revision:Long):OcrReading=gate.withLock {
        val root=File(context.noBackupFilesDir,"ocr")
        install(context,root)
        val api=TessBaseAPI()
        try {
            if(!api.init(root.absolutePath,"rus",TessBaseAPI.OEM_LSTM_ONLY))
                throw IOException("Не удалось запустить русский OCR.")
            api.setPageSegMode(TessBaseAPI.PageSegMode.PSM_AUTO)
            api.setImage(bitmap)
            api.getUTF8Text() // Recognize before requesting the reading-order iterator.
            val found=mutableListOf<OcrSourceLine>()
            val iterator=api.resultIterator
            if(iterator!=null) {
                try {
                    iterator.begin()
                    do {
                        val txt=iterator.getUTF8Text(PageIteratorLevel.RIL_TEXTLINE)?.trim()
                        val conf=iterator.confidence(PageIteratorLevel.RIL_TEXTLINE)
                        val rect=iterator.getBoundingRect(PageIteratorLevel.RIL_TEXTLINE)
                        if(!txt.isNullOrBlank()&&txt.length<=2048&&rect!=null &&
                            rect.left>=0&&rect.top>=0&&rect.right>rect.left&&rect.bottom>rect.top &&
                            conf.isFinite()&&conf in 0f..100f)
                            found.add(OcrSourceLine(found.size,txt,OcrLineBox(
                                rect.left,rect.top,rect.right,rect.bottom),
                                (conf*100).roundToInt().coerceIn(0,10000)))
                    } while(found.size<3000&&iterator.next(PageIteratorLevel.RIL_TEXTLINE))
                } finally { iterator.delete() }
            }
            val input=ReceiptOcrEvidence.build(revision,found)
            OcrReading(input,ReceiptTotalReview.prepare(input),found.size)
        } finally { api.recycle() }
    }

    private fun install(context:Context,root:File) {
        val dir=File(root,"tessdata")
        if(!dir.isDirectory&&!dir.mkdirs())throw IOException("Нет доступа к хранилищу OCR.")
        val destination=File(dir,MODEL)
        if(destination.isFile&&valid(destination))return
        val tmp=File(dir,"rus.traineddata.tmp")
        try {
            context.assets.open("tessdata/$MODEL").use{source->
                tmp.outputStream().use{output->source.copyTo(output)}
            }
            if(!valid(tmp))throw IOException("Модель русского OCR повреждена.")
            if(destination.exists()&&!destination.delete())throw IOException("Нельзя обновить OCR-модель.")
            if(!tmp.renameTo(destination))throw IOException("Нельзя установить OCR-модель.")
        } finally { tmp.delete() }
    }

    private fun valid(file:File):Boolean {
        if(file.length()!=BYTES)return false
        val md=MessageDigest.getInstance("SHA-512")
        file.inputStream().use {stream->
            val buf=ByteArray(32768)
            while(true){val n=stream.read(buf);if(n<0)break;md.update(buf,0,n)}
        }
        return md.digest().joinToString(""){"%02x".format(it)}==SHA512
    }
}
