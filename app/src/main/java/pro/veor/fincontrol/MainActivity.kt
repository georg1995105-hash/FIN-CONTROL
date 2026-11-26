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
        activeSource = uri
        loading = true
        failure = null
        lifecycleScope.launch {
            try {
                // Capture an immutable URI value: changing a document never
                // overwrites a newer preview with the previous decode.
                val result = withContext(Dispatchers.IO) {
                    DocumentLoader.open(this@MainActivity, uri, pageIndex)
                }
                if (uri == activeSource) loaded = result
            } catch (e: Exception) {
                if (uri == activeSource) {
                    failure = "Не удалось прочитать документ: " + (e.localizedMessage ?: "ошибка файла")
                }
            } finally {
                if (uri == activeSource) loading = false
            }
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        pendingCamera?.let { outState.putString("pendingCamera", it.toString()) }
        super.onSaveInstanceState(outState)
    }
}
