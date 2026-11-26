package pro.veor.fincontrol

import android.content.ActivityNotFoundException
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.FileProvider
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import fincontrol.core.DemoInvoiceCase
import java.io.File

/**
 * No internet permission, remote APIs, financial guesses or paid services.
 * System camera and SAF give this initial shell real offline inputs.
 */
class MainActivity : ComponentActivity() {
    private var loaded by androidx.compose.runtime.mutableStateOf<LoadedDocument?>(null)
    private var loading by androidx.compose.runtime.mutableStateOf(false)
    private var failure by androidx.compose.runtime.mutableStateOf<String?>(null)
    private var activeSource: Uri? = null
    private var openGeneration: Long = 0
    private var pendingCamera: Uri? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        pendingCamera = savedInstanceState?.getString("pendingCamera")?.let(Uri::parse)
        val prefs = getSharedPreferences("fin_control_ui", MODE_PRIVATE)
        setContent {
            var selectedTheme by androidx.compose.runtime.saveable.rememberSaveable {
                androidx.compose.runtime.mutableStateOf(prefs.getString("theme", "graphite") ?: "graphite")
            }
            val filePicker = androidx.activity.compose.rememberLauncherForActivityResult(
                ActivityResultContracts.OpenDocument()
            ) { uri ->
                if (uri != null) openSource(uri)
            }
            val camera = androidx.activity.compose.rememberLauncherForActivityResult(
                ActivityResultContracts.TakePicture()
            ) { saved ->
                val uri = pendingCamera
                pendingCamera = null
                if (saved && uri != null) openSource(uri)
                else failure = "Камера не сохранила снимок."
            }
            FinApp(
                themeId = selectedTheme,
                document = loaded,
                isLoading = loading,
                error = failure,
                onImport = {
                    try {
                        filePicker.launch(arrayOf("image/*", "application/pdf"))
                    } catch (_: ActivityNotFoundException) {
                        failure = "На устройстве нет приложения для выбора файлов."
                    }
                },
                onDemo = { sample -> openDemo(sample) },
                onCamera = {
                    try {
                        val folder = File(cacheDir, "captures").apply { mkdirs() }
                        val output = File.createTempFile("fin-control-", ".jpg", folder)
                        val uri = FileProvider.getUriForFile(
                            this, "$packageName.fileprovider", output
                        )
                        pendingCamera = uri
                        camera.launch(uri)
                    } catch (e: Exception) {
                        pendingCamera = null
                        failure = "Не удалось открыть камеру: " + (e.localizedMessage ?: "недоступно")
                    }
                },
                onChangePage = { index ->
                    activeSource?.let { openSource(it, index) }
                },
                onTheme = { theme ->
                    selectedTheme = theme
                    prefs.edit().putString("theme", theme).apply()
                },
                onClearError = { failure = null }
            )
        }
    }

    private fun openSource(uri: Uri, pageIndex: Int = 0) {
        // The same URI may deliver multiple PDF pages; guard by request, not URI.
        val request = ++openGeneration
        activeSource = uri
        loaded = null
        loading = true
        failure = null
        lifecycleScope.launch {
            try {
                // Capture an immutable URI value: changing a document never
                // overwrites a newer preview with the previous decode.
                val result = withContext(Dispatchers.IO) {
                    DocumentLoader.open(this@MainActivity, uri, pageIndex)
                }
                if (request == openGeneration && uri == activeSource) loaded = result
            } catch (e: Exception) {
                if (request == openGeneration && uri == activeSource) {
                    failure = "Не удалось прочитать документ: " + (e.localizedMessage ?: "ошибка файла")
                }
            } finally {
                if (request == openGeneration && uri == activeSource) loading = false
            }
        }
    }

    private fun openDemo(sample: DemoInvoiceCase) {
        val request = ++openGeneration
        activeSource = null
        loaded = null
        loading = true
        failure = null
        lifecycleScope.launch {
            try {
                val result = withContext(Dispatchers.Default) {
                    DemoInvoiceFactory.create(sample)
                }
                if (request == openGeneration) loaded = result
            } catch (e: Exception) {
                if (request == openGeneration) {
                    failure = "Не удалось создать учебный счёт: " +
                        (e.localizedMessage ?: "ошибка")
                }
            } finally {
                if (request == openGeneration) loading = false
            }
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        pendingCamera?.let { outState.putString("pendingCamera", it.toString()) }
        super.onSaveInstanceState(outState)
    }
}
