package pro.veor.phantomcontrol

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import java.util.UUID

class MainActivity : ComponentActivity() {
    private lateinit var state: ControlState
    override fun onStart() { super.onStart(); state.startPolling() }
    override fun onStop() { state.stopPolling(); super.onStop() }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        state = ViewModelProvider(this)[ControlState::class.java]
        val prefs = getSharedPreferences("appearance", MODE_PRIVATE)
        setContent {
            var theme by rememberSaveable { mutableStateOf(prefs.getString("theme","auto") ?: "auto") }
            val dark = isSystemInDarkTheme()
            val scheme = when(theme) {
                "navy" -> darkColorScheme(primary=Color(0xFFAEC5E4),background=Color(0xFF111823),surface=Color(0xFF202C3E))
                "graphite" -> darkColorScheme(primary=Color(0xFFBFCBDA),background=Color(0xFF141619),surface=Color(0xFF22262B))
                "light" -> lightColorScheme(primary=Color(0xFF395D87),background=Color(0xFFF0F2F4),surface=Color(0xFFE5E8ED))
                else -> if(dark) darkColorScheme(primary=Color(0xFFBFCBDA),background=Color(0xFF141619),surface=Color(0xFF22262B)) else lightColorScheme(primary=Color(0xFF395D87),background=Color(0xFFF0F2F4),surface=Color(0xFFE5E8ED))
            }
            MaterialTheme(colorScheme=scheme) {
                ControlScreen(state,theme) { theme=it; prefs.edit().putString("theme",it).apply() }
            }
        }
    }
}
class ControlState : ViewModel() {
    var origin by mutableStateOf("")
    var token by mutableStateOf("")
    var snapshot by mutableStateOf<Snapshot?>(null); private set
    var error by mutableStateOf<String?>(null); private set
    var busy by mutableStateOf(false); private set
    var stale by mutableStateOf(true); private set
    var draft by mutableStateOf("")
    var kind by mutableStateOf("diagnose")
    var model by mutableStateOf("")
    private var lastSubmission: Pair<List<String>,String>? = null
    private var api: ControlApi? = null
    private var polling: Job? = null
    fun startPolling() {
        if(polling?.isActive==true)return
        polling=viewModelScope.launch {
            while(true){
                delay(if(stale)30000L else 10000L)
                if(snapshot!=null && api!=null && !busy)refresh()
            }
        }
    }
    fun stopPolling(){polling?.cancel();polling=null}
    fun disconnect() {
        if(busy) return
        token="";api=null;snapshot=null;stale=true;error=null;lastSubmission=null
    }
    fun connect() {
        if(busy) return
        api=null;snapshot=null;stale=true
        try { api=ControlApi(origin,token) } catch (_:Exception) {
            error="Введите корректный HTTPS-адрес и токен доступа."; return
        }
        refresh()
    }
    fun refresh() {
        val client=api ?: return
        runWork { val v=withContext(Dispatchers.IO){client.snapshot()}
            snapshot=v;stale=false
            if(v.capabilities.none{it.kind==kind})kind=v.capabilities.firstOrNull()?.kind ?: ""
            val models=v.capabilities.firstOrNull{it.kind==kind}?.models.orEmpty()
            if(model !in models)model=models.firstOrNull() ?: ""
        }
    }
    fun submit() {
        val client=api ?: return
        if(stale || busy || draft.isBlank() || draft.length>4000) return
        if(snapshot?.capabilities?.none{it.kind==kind && model in it.models} != false) return
        val content=listOf(kind,model,draft.trim())
        val id=lastSubmission?.takeIf{it.first==content}?.second ?: UUID.randomUUID().toString()
        lastSubmission=content to id
        runWork {
            withContext(Dispatchers.IO){client.submit(id,content[0],content[1],content[2])}
            lastSubmission=null;draft=""
            snapshot=withContext(Dispatchers.IO){client.snapshot()};stale=false
        }
    }
    private fun runWork(action:suspend ()->Unit){
        if(busy)return
        busy=true;error=null
        viewModelScope.launch {
            try{action()}catch(e:CancellationException){throw e}
            catch(e:Exception){
                stale=true
                if(e is ApiHttpException && e.status==401){api=null;snapshot=null;token="";error="Сеанс недействителен. Подключитесь снова."}
                else error=if(e is ApiHttpException)e.message else "Связь или формат ответа недоступны. Проверьте подключение."
            }
            finally{busy=false}
        }
    }
}
private val titles=listOf("Главная","Задачи","Чат","Настройки")
private fun statusLabel(value:String)=when(value){
    "ok"->"Работает";"degraded"->"Нестабильно";"failed"->"Ошибка";"unknown"->"Не проверено"
    "queued"->"В очереди";"running"->"Выполняется";"succeeded"->"Завершено";"needs_review"->"Требуется проверка"
    "disabled"->"Выключен";else->value
}
private fun kindLabel(value:String)=when(value){"diagnose"->"Диагностика (только чтение)";"develop"->"Разработка";"chat"->"Чат";else->value}
private fun modelLabel(value:String)=if(value=="local-readonly")"Штатная диагностика" else value
@Composable private fun ControlScreen(s:ControlState,theme:String,onTheme:(String)->Unit){
    var page by rememberSaveable { mutableIntStateOf(0) }
    BackHandler(page!=0){page=0}
    val icons=listOf(Icons.Filled.Home,Icons.Filled.List,Icons.Filled.List,Icons.Filled.Settings)
    BoxWithConstraints(Modifier.fillMaxSize().safeDrawingPadding()){
        if(maxWidth>=700.dp){
            Row(Modifier.fillMaxSize()){
                NavigationRail { titles.forEachIndexed{i,t->NavigationRailItem(page==i,{page=i},{Icon(icons[i],t)},label={Text(t)})} }
                Body(Modifier.weight(1f),s,page,theme,onTheme,{page=it})
            }
        }else{
            Scaffold(bottomBar={NavigationBar{titles.forEachIndexed{i,t->NavigationBarItem(page==i,{page=i},{Icon(icons[i],t)},label={Text(t)})}}}){
                Body(Modifier.padding(it),s,page,theme,onTheme,{page=it})
            }
        }
    }
}
@Composable private fun Body(modifier:Modifier,s:ControlState,page:Int,theme:String,onTheme:(String)->Unit,navigate:(Int)->Unit){
    Column(modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),verticalArrangement=Arrangement.spacedBy(12.dp)){
        Row(verticalAlignment=Alignment.CenterVertically){
            Text(if(page==0)"PHANTOM CONTROL" else titles[page],style=MaterialTheme.typography.headlineSmall,modifier=Modifier.weight(1f))
            IconButton(onClick={s.refresh()},enabled=!s.busy && s.snapshot!=null){Icon(Icons.Filled.Refresh,"Обновить")}
        }
        if(s.busy)LinearProgressIndicator(Modifier.fillMaxWidth())
        s.error?.let{Text(it,color=MaterialTheme.colorScheme.error)}
        if(s.stale)Text("Нет актуальных данных сервера",color=MaterialTheme.colorScheme.onSurfaceVariant)
        val snap=s.snapshot
        when(page){
            0 -> {
                if(snap==null){Text("Подключите персональный сервер управления.");Button(onClick={navigate(3)}){Text("Подключение")}}
                else{
                    Text("Последнее наблюдение: "+snap.observedAt.ifBlank{"Нет данных"})
                    Text("Автопилот: "+statusLabel(snap.autopilot))
                    if(snap.services.isEmpty())Text("Нет подтверждённых наблюдений.")
                    snap.services.forEach{item->
                        Card(Modifier.fillMaxWidth()){Column(Modifier.padding(14.dp)){Text(item.name,style=MaterialTheme.typography.titleMedium);Text(if(s.stale)"Данные устарели" else statusLabel(item.state));Text(if(s.stale)"Обновите подключение" else item.detail)}}
                    }
                    Button(onClick={navigate(1)}){Text("Задачи")}
                }
            }
            1,2 -> {
                val available=snap?.capabilities.orEmpty().filter{if(page==2)it.kind=="chat" else it.kind!="chat"}
                if(available.isEmpty())Text("Сервер пока не предоставил доступного исполнителя.")
                else{
                    val selected=available.firstOrNull{it.kind==s.kind} ?: available.first()
                    LaunchedEffect(selected.kind){s.kind=selected.kind;if(s.model !in selected.models)s.model=selected.models.firstOrNull()?:""}
                    Text("Тип задачи")
                    available.forEach{c-> FilterChip(c.kind==s.kind,{s.kind=c.kind;s.model=c.models.firstOrNull()?:""},{Text(kindLabel(c.kind))})}
                    Text("Исполнитель")
                    selected.models.forEach{m-> FilterChip(m==s.model,{s.model=m},{Text(modelLabel(m))})}
                    OutlinedTextField(s.draft,{s.draft=it},Modifier.fillMaxWidth(),label={Text("Поручение")},minLines=3)
                    Button(onClick={s.submit()},enabled=!s.busy&&!s.stale&&s.draft.isNotBlank()&&s.model in selected.models){Text("Запустить")}
                }
                Text("История задач",style=MaterialTheme.typography.titleLarge)
                val tasks=snap?.tasks.orEmpty().filter{if(page==2)it.kind=="chat" else it.kind!="chat"}
                if(tasks.isEmpty())Text("Задач нет.")
                tasks.forEach{t->Card(Modifier.fillMaxWidth()){Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(5.dp)){Text(t.title,style=MaterialTheme.typography.titleMedium);Text(statusLabel(t.state));if(t.result.isNotBlank())Text(t.result);Text(t.id,style=MaterialTheme.typography.bodySmall)}}}
            }
            3 -> {
                Text("Сервер управления")
                OutlinedTextField(s.origin,{s.origin=it},Modifier.fillMaxWidth(),label={Text("HTTPS-адрес")},singleLine=true,enabled=!s.busy&&snap==null)
                OutlinedTextField(s.token,{s.token=it},Modifier.fillMaxWidth(),label={Text("Токен доступа")},singleLine=true,visualTransformation=PasswordVisualTransformation(),enabled=!s.busy&&snap==null)
                Text("Токен хранится только в памяти текущего сеанса.")
                Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){
                    Button(onClick={s.connect()},enabled=!s.busy&&snap==null){Text("Подключить")}
                    OutlinedButton(onClick={s.disconnect()},enabled=!s.busy){Text("Отключить")}
                }
                Text("Тема оформления",style=MaterialTheme.typography.titleLarge)
                listOf("auto" to "Авто","graphite" to "Графит","navy" to "Тёмно-синяя","light" to "Светлая").forEach{(key,label)->FilterChip(theme==key,{onTheme(key)},{Text(label)})}
            }
        }
    }
}
