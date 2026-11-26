package pro.veor.fincontrol

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.ui.res.painterResource
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private val graphite = darkColorScheme(
    primary = Color(0xFFB9CFC2), onPrimary = Color(0xFF17251F),
    background = Color(0xFF141619), onBackground = Color(0xFFF1F2F4),
    surface = Color(0xFF22262B), onSurface = Color(0xFFF1F2F4),
    surfaceVariant = Color(0xFF2D3338), onSurfaceVariant = Color(0xFFA1A7AE),
    outline = Color(0xFF353A40), error = Color(0xFFD4AF7B)
)
private val forest = darkColorScheme(
    primary = Color(0xFFADC8B6), onPrimary = Color(0xFF17251F),
    background = Color(0xFF101A15), onBackground = Color(0xFFEDF4EF),
    surface = Color(0xFF1E2C24), onSurface = Color(0xFFEDF4EF),
    surfaceVariant = Color(0xFF293B30), onSurfaceVariant = Color(0xFFA0B0A6),
    outline = Color(0xFF35453C), error = Color(0xFFD4AF7B)
)
private val navy = darkColorScheme(
    primary = Color(0xFFAEC5E4), onPrimary = Color(0xFF172638),
    background = Color(0xFF111823), onBackground = Color(0xFFEDF2FA),
    surface = Color(0xFF202C3E), onSurface = Color(0xFFEDF2FA),
    surfaceVariant = Color(0xFF29394D), onSurfaceVariant = Color(0xFF9EADC1),
    outline = Color(0xFF354459), error = Color(0xFFD4AF7B)
)
private val light = lightColorScheme(
    primary = Color(0xFF416C5D), onPrimary = Color.White,
    background = Color(0xFFF0F2F4), onBackground = Color(0xFF222930),
    surface = Color.White, onSurface = Color(0xFF222930),
    surfaceVariant = Color(0xFFE6E9EB), onSurfaceVariant = Color(0xFF606B75),
    outline = Color(0xFFD9DEE2), error = Color(0xFF986322)
)

private const val HOME = "home"
private const val AUDIT = "audit"
private const val VISION = "vision"
private const val CAMERA = "camera"
private const val DOCUMENT = "document"
private const val HISTORY = "history"
private const val PRO = "pro"
private const val SETTINGS = "settings"

private data class Tab(val key: String, val label: String, val icon: Int)
private val tabs = listOf(
    Tab(HOME, "Главная", R.drawable.ic_home),
    Tab(HISTORY, "История", R.drawable.ic_history),
    Tab(PRO, "PRO", R.drawable.ic_star),
    Tab(SETTINGS, "Настройки", R.drawable.ic_settings)
)

@Composable
fun FinApp(
    themeId: String,
    document: LoadedDocument?,
    isLoading: Boolean,
    error: String?,
    onImport: () -> Unit,
    onCamera: () -> Unit,
    onChangePage: (Int) -> Unit,
    onTheme: (String) -> Unit,
    onClearError: () -> Unit
) {
    val scheme = when (themeId) {
        "green" -> forest
        "navy" -> navy
        "light" -> light
        else -> graphite
    }
    var page by rememberSaveable { mutableStateOf(HOME) }
    LaunchedEffect(document) { if (document != null) page = DOCUMENT }
    BackHandler(enabled = page != HOME) { page = HOME }

    MaterialTheme(colorScheme = scheme) {
        Surface(modifier = Modifier.fillMaxSize(), color = scheme.background) {
            BoxWithConstraints(Modifier.fillMaxSize().safeDrawingPadding()) {
                val tablet = maxWidth >= 700.dp
                if (tablet) {
                    Row {
                        NavigationRail(
                            containerColor = scheme.surface,
                            modifier = Modifier.fillMaxHeight()
                        ) {
                            Spacer(Modifier.height(20.dp))
                            tabs.forEach { tab ->
                                NavigationRailItem(
                                    selected = page == tab.key,
                                    onClick = { page = tab.key },
                                    icon = { Icon(painterResource(tab.icon), contentDescription = tab.label) },
                                    label = { Text(tab.label) },
                                    alwaysShowLabel = true
                                )
                            }
                        }
                        AppBody(
                            modifier = Modifier.weight(1f),
                            page = page, onPage = { page = it }, document = document,
                            isLoading = isLoading, error = error,
                            onImport = onImport, onCamera = onCamera,
                            onChangePage = onChangePage, onTheme = onTheme,
                            themeId = themeId, onClearError = onClearError
                        )
                    }
                } else {
                    Scaffold(
                        containerColor = scheme.background,
                        bottomBar = {
                            NavigationBar(containerColor = scheme.surface) {
                                tabs.forEach { tab ->
                                    NavigationBarItem(
                                        selected = page == tab.key,
                                        onClick = { page = tab.key },
                                        icon = { Icon(painterResource(tab.icon), contentDescription = tab.label) },
                                        label = { Text(tab.label, maxLines = 1) }
                                    )
                                }
                            }
                        }
                    ) { padding ->
                        AppBody(
                            modifier = Modifier.padding(padding),
                            page = page, onPage = { page = it }, document = document,
                            isLoading = isLoading, error = error,
                            onImport = onImport, onCamera = onCamera,
                            onChangePage = onChangePage, onTheme = onTheme,
                            themeId = themeId, onClearError = onClearError
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun AppBody(
    modifier: Modifier,
    page: String,
    onPage: (String) -> Unit,
    document: LoadedDocument?,
    isLoading: Boolean,
    error: String?,
    onImport: () -> Unit,
    onCamera: () -> Unit,
    onChangePage: (Int) -> Unit,
    onTheme: (String) -> Unit,
    themeId: String,
    onClearError: () -> Unit
) {
    Column(modifier = modifier.fillMaxSize()) {
        Header(page, onPage)
        if (isLoading) LinearProgressIndicator(Modifier.fillMaxWidth())
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 18.dp, vertical = 16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            if (error != null) {
                Surface(
                    color = MaterialTheme.colorScheme.surfaceVariant,
                    shape = RoundedCornerShape(14.dp)
                ) {
                    Row(
                        Modifier.fillMaxWidth().padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(error, modifier = Modifier.weight(1f),
                            color = MaterialTheme.colorScheme.error)
                        TextButton(onClick = onClearError) { Text("Закрыть") }
                    }
                }
            }
            when (page) {
                HOME -> HomeContent(onPage, onCamera, onImport)
                AUDIT -> ScenarioContent(
                    "Финансовый контроль",
                    "Чеки, счета, сметы и документы",
                    R.drawable.ic_receipt,
                    "Импортируйте фото или PDF. На текущем этапе доступен реальный просмотр документа; локальное распознавание и анализ сумм ещё не интегрированы.",
                    onImport, onCamera
                )
                VISION -> ScenarioContent(
                    "Компьютерное зрение",
                    "Объекты, маркировка и комплектность",
                    R.drawable.ic_eye,
                    "Откройте фотографию или камеру. Подсчёт объектов и сравнение с эталоном ещё не интегрированы — приложение не показывает выдуманные результаты.",
                    onImport, onCamera
                )
                CAMERA -> ScenarioContent(
                    "Интеллектуальная камера",
                    "Съёмка через приложение камеры устройства",
                    R.drawable.ic_camera,
                    "Снимок остаётся на устройстве. После съёмки откроется предпросмотр; автономная обработка изображения будет добавлена отдельно.",
                    onImport, onCamera
                )
                DOCUMENT -> DocumentContent(document, onImport, onCamera, onChangePage)
                HISTORY -> EmptyContent(
                    R.drawable.ic_history, "История проверок",
                    "Проверки ещё не выполняются, поэтому история пустая. Мы не создаём фиктивные записи."
                )
                PRO -> EmptyContent(
                    R.drawable.ic_star, "FIN CONTROL PRO",
                    "Оплата и лицензирование пока не подключены. Покупки не предлагаются до проверки всех функций и условий."
                )
                SETTINGS -> SettingsContent(themeId, onTheme)
            }
        }
    }
}

@Composable
private fun Header(page: String, onPage: (String) -> Unit) {
    val name = when (page) {
        HOME -> "FIN CONTROL"
        AUDIT -> "Финансовый контроль"
        VISION -> "Компьютерное зрение"
        CAMERA -> "Камера"
        DOCUMENT -> "Документ"
        HISTORY -> "История"
        PRO -> "PRO"
        else -> "Настройки"
    }
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        if (page !in listOf(HOME, HISTORY, PRO, SETTINGS)) {
            IconButton(onClick = { onPage(HOME) }) {
                Icon(painterResource(R.drawable.ic_back), contentDescription = "Назад")
            }
        }
        Text(name, style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
        if (page == HOME) {
            IconButton(onClick = { onPage(CAMERA) }) {
                Icon(painterResource(R.drawable.ic_camera), contentDescription = "Открыть камеру")
            }
        }
    }
    HorizontalDivider(color = MaterialTheme.colorScheme.outline)
}

@Composable
private fun HomeContent(onPage: (String) -> Unit, onCamera: () -> Unit, onImport: () -> Unit) {
    Text(
        "Контроль без догадок",
        style = MaterialTheme.typography.headlineSmall,
        fontWeight = FontWeight.SemiBold
    )
    Text(
        "Финансовые документы и визуальные проверки — в одном приложении.",
        color = MaterialTheme.colorScheme.onSurfaceVariant
    )
    ActionCard(
        title = "Компьютерное зрение",
        caption = "Фото, объекты, комплектность",
        icon = R.drawable.ic_eye,
        onClick = { onPage(VISION) }
    )
    ActionCard(
        title = "Финансовый контроль",
        caption = "Чеки, счета и сметы",
        icon = R.drawable.ic_receipt,
        onClick = { onPage(AUDIT) }
    )
    Spacer(Modifier.height(4.dp))
    Text("Начать с документа", style = MaterialTheme.typography.titleMedium,
        fontWeight = FontWeight.SemiBold)
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Button(
            onClick = onCamera, modifier = Modifier.weight(1f).heightIn(min = 52.dp),
            shape = RoundedCornerShape(14.dp)
        ) {
            Icon(painterResource(R.drawable.ic_camera), contentDescription = null)
            Spacer(Modifier.width(8.dp))
            Text("Камера")
        }
        OutlinedButton(
            onClick = onImport, modifier = Modifier.weight(1f).heightIn(min = 52.dp),
            shape = RoundedCornerShape(14.dp)
        ) {
            Icon(painterResource(R.drawable.ic_upload), contentDescription = null)
            Spacer(Modifier.width(8.dp))
            Text("Импорт")
        }
    }
    Informational(
        "Этап разработки",
        "Фото и PDF открываются локально. Автоматический финансовый анализ и подсчёт объектов пока не доступны."
    )
}

@Composable
private fun ActionCard(
    title: String, caption: String, icon: Int, onClick: () -> Unit
) {
    Surface(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        color = MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(20.dp)
    ) {
        Row(
            Modifier.fillMaxWidth().padding(18.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                Modifier.size(58.dp)
                    .clip(RoundedCornerShape(14.dp))
                    .background(MaterialTheme.colorScheme.surfaceVariant),
                contentAlignment = Alignment.Center
            ) {
                Icon(painterResource(icon), contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(28.dp))
            }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(title, style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(4.dp))
                Text(caption, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodySmall)
            }
            Icon(painterResource(R.drawable.ic_chevron), contentDescription = null,
                tint = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun ScenarioContent(
    title: String, subtitle: String, icon: Int,
    explanation: String,
    onImport: () -> Unit, onCamera: () -> Unit
) {
    Surface(
        shape = RoundedCornerShape(20.dp),
        color = MaterialTheme.colorScheme.surface,
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(
            Modifier.padding(22.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Icon(painterResource(icon), contentDescription = null,
                modifier = Modifier.size(40.dp),
                tint = MaterialTheme.colorScheme.primary)
            Text(title, style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.SemiBold)
            Text(subtitle, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Button(
                onClick = onCamera,
                modifier = Modifier.fillMaxWidth().heightIn(min = 50.dp),
                shape = RoundedCornerShape(13.dp)
            ) {
                Icon(painterResource(R.drawable.ic_camera), contentDescription = null)
                Spacer(Modifier.width(10.dp))
                Text("Сделать снимок")
            }
            OutlinedButton(
                onClick = onImport,
                modifier = Modifier.fillMaxWidth().heightIn(min = 50.dp),
                shape = RoundedCornerShape(13.dp)
            ) {
                Icon(painterResource(R.drawable.ic_upload), contentDescription = null)
                Spacer(Modifier.width(10.dp))
                Text("Открыть фото или PDF")
            }
        }
    }
    Informational("Доступность", explanation)
}

@Composable
private fun DocumentContent(
    document: LoadedDocument?,
    onImport: () -> Unit,
    onCamera: () -> Unit,
    onChangePage: (Int) -> Unit
) {
    if (document == null) {
        EmptyContent(R.drawable.ic_document, "Документ не открыт",
            "Импортируйте изображение или сделайте снимок, чтобы увидеть его здесь.")
        Button(onClick = onImport, modifier = Modifier.fillMaxWidth()) {
            Text("Выбрать документ")
        }
        return
    }
    Text(document.displayName, style = MaterialTheme.typography.titleMedium,
        maxLines = 2, overflow = TextOverflow.Ellipsis)
    Text(
        document.kind + if (document.pages > 1)
            " · Страница " + (document.pageIndex + 1) + " из " + document.pages
            else " · Одна страница",
        color = MaterialTheme.colorScheme.onSurfaceVariant
    )
    Surface(
        shape = RoundedCornerShape(18.dp),
        color = MaterialTheme.colorScheme.surfaceVariant,
        modifier = Modifier.fillMaxWidth()
    ) {
        Image(
            bitmap = document.preview.asImageBitmap(),
            contentDescription = "Предпросмотр документа",
            modifier = Modifier.fillMaxWidth().heightIn(min = 160.dp, max = 470.dp)
                .padding(8.dp),
            contentScale = ContentScale.Fit
        )
    }
    if (document.pages > 1) {
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            OutlinedButton(
                onClick = { onChangePage(document.pageIndex - 1) },
                enabled = document.pageIndex > 0,
                modifier = Modifier.weight(1f)
            ) { Text("Назад") }
            OutlinedButton(
                onClick = { onChangePage(document.pageIndex + 1) },
                enabled = document.pageIndex + 1 < document.pages,
                modifier = Modifier.weight(1f)
            ) { Text("Следующая") }
        }
    }
    Informational(
        "Проверка документа",
        "Снимок открыт локально, но сумма и позиции ещё не распознаны. Результат финансовой проверки не сформирован."
    )
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        OutlinedButton(onClick = onImport, modifier = Modifier.weight(1f)) {
            Text("Другой файл")
        }
        OutlinedButton(onClick = onCamera, modifier = Modifier.weight(1f)) {
            Text("Новый снимок")
        }
    }
}

@Composable
private fun Informational(title: String, body: String) {
    Surface(
        color = MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(16.dp)
    ) {
        Row(Modifier.fillMaxWidth().padding(15.dp), verticalAlignment = Alignment.Top) {
            Icon(painterResource(R.drawable.ic_info), contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(10.dp))
            Column {
                Text(title, style = MaterialTheme.typography.labelLarge,
                    fontWeight = FontWeight.Medium)
                Spacer(Modifier.height(5.dp))
                Text(body, style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun EmptyContent(icon: Int, title: String, explanation: String) {
    Surface(
        color = MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(20.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(
            Modifier.fillMaxWidth().padding(26.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Icon(painterResource(icon), contentDescription = null,
                tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(42.dp))
            Spacer(Modifier.height(12.dp))
            Text(title, style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(8.dp))
            Text(explanation, style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun SettingsContent(themeId: String, onTheme: (String) -> Unit) {
    Text("Оформление", style = MaterialTheme.typography.titleLarge,
        fontWeight = FontWeight.SemiBold)
    Text("Выберите тему. Настройка сохраняется на устройстве.",
        color = MaterialTheme.colorScheme.onSurfaceVariant)
    val choices = listOf(
        Triple("graphite", "Графит", Color(0xFF141619)),
        Triple("green", "Тёмно-зелёная", Color(0xFF101A15)),
        Triple("navy", "Тёмно-синяя", Color(0xFF111823)),
        Triple("light", "Светлая", Color(0xFFF0F2F4))
    )
    choices.forEach { (key, label, swatch) ->
        Surface(
            modifier = Modifier.fillMaxWidth().clickable { onTheme(key) },
            shape = RoundedCornerShape(15.dp),
            color = MaterialTheme.colorScheme.surface
        ) {
            Row(
                Modifier.fillMaxWidth().padding(14.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Box(
                    Modifier.size(38.dp).clip(RoundedCornerShape(9.dp))
                        .background(swatch)
                )
                Spacer(Modifier.width(12.dp))
                Text(label, modifier = Modifier.weight(1f))
                RadioButton(selected = key == themeId, onClick = { onTheme(key) })
            }
        }
    }
    Spacer(Modifier.height(8.dp))
    Informational(
        "Конфиденциальность",
        "Документы не передаются в сеть. Резервное копирование отключено. История и оплата пока не реализованы."
    )
    Informational("Версия", "0.1.0-alpha01 · Первая Android-оболочка")
}
