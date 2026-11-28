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
    var pairingCode by mutableStateOf("")
    var connected by mutableStateOf(false); private set
    var snapshot by mutableStateOf<Snapshot?>(null); private set
    var error by mutableStateOf<String?>(null); private set
    var busy by mutableStateOf(false); private set
    var stale by mutableStateOf(true); private set
    var draft by mutableStateOf("")
    var chatDraft by mutableStateOf("")
    var chatParent by mutableStateOf<Task?>(null); private set
    var pendingChat by mutableStateOf<String?>(null); private set
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
                if(connected && api!=null && !busy)refresh()
            }
        }
    }
    fun stopPolling(){polling?.cancel();polling=null}
    private fun clearSession() {
        pairingCode="";api=null;snapshot=null;connected=false;stale=true;lastSubmission=null
        draft="";chatDraft="";chatParent=null;pendingChat=null;model=""
    }
    fun disconnect() {
        if(busy) return
        val client=api
        if(client==null){clearSession();error=null;return}
        runWork {
            try {
                withContext(Dispatchers.IO){client.revoke()}
                clearSession()
            } catch(e:CancellationException){throw e}
            catch(e:Exception) {
                clearSession()
                if(e !is ApiHttpException || e.status!=401)
                    error="Локальный выход выполнен. Отзыв на сервере не подтверждён; срок сеанса ограничен 12 часами."
            }
        }
    }
    fun connect() {
        if(busy || connected) return
        val address=try{ControlEndpoint.normalize(origin)}catch(_:Exception){
            error="Введите корректный HTTPS-адрес.";return
        }
        val code=pairingCode.trim()
        if(!code.matches(Regex("[A-Za-z0-9_-]{43}"))){error="Введите одноразовый код подключения.";return}
        pairingCode=""
        runWork {
            val client=withContext(Dispatchers.IO){ControlApi.pair(address,code)}
            api=client;connected=true;origin=address
            applySnapshot(withContext(Dispatchers.IO){client.snapshot()})
        }
    }
    private fun applySnapshot(v:Snapshot) {
        snapshot=v;stale=false
        val pending=v.tasks.firstOrNull{it.id==pendingChat}
        if(pending?.state=="succeeded"){chatParent=pending;pendingChat=null}
        else if(pending!=null && pending.state in setOf("failed","needs_review","cancelled"))pendingChat=null
        if(v.capabilities.none{it.kind==kind})kind=v.capabilities.firstOrNull()?.kind ?: ""
        val models=v.capabilities.firstOrNull{it.kind==kind}?.models.orEmpty()
        if(model !in models)model=models.firstOrNull() ?: ""
    }
    fun refresh() {
        val client=api ?: return
        runWork { applySnapshot(withContext(Dispatchers.IO){client.snapshot()}) }
    }
    fun selectConversation(parent:Task?) {
        if(busy)return
        if(parent!=null && (parent.kind!="chat" || parent.state!="succeeded" || snapshot?.features?.contains("chat_parent")!=true))return
        chatParent=parent;pendingChat=null
    }
    fun submit(selectedKind:String,selectedModel:String) {
        val client=api ?: return
        val isChat=selectedKind=="chat"
        val message=if(isChat)chatDraft else draft
        if(stale || busy || message.isBlank() || message.length>4000 || (isChat && pendingChat!=null)) return
        if(snapshot?.capabilities?.none{it.kind==selectedKind && selectedModel in it.models} != false) return
        val parent=if(isChat && snapshot?.features?.contains("chat_parent")==true)chatParent?.id else null
        val content=listOf(selectedKind,selectedModel,message.trim(),parent.orEmpty())
        val id=lastSubmission?.takeIf{it.first==content}?.second ?: UUID.randomUUID().toString()
        lastSubmission=content to id
        runWork {
            withContext(Dispatchers.IO){client.submit(id,content[0],content[1],content[2],parent)}
            lastSubmission=null
            if(isChat){chatDraft="";if(snapshot?.features?.contains("chat_parent")==true)pendingChat=id}
            else draft=""
            applySnapshot(withContext(Dispatchers.IO){client.snapshot()})
        }
    }
    fun cancel(task:Task) {
        val client=api ?: return
        if(busy || stale || task.state!="queued" || snapshot?.features?.contains("cancel_queued")!=true)return
        runWork {
            try { withContext(Dispatchers.IO){client.cancel(task.id)} }
            catch(e:ApiHttpException){
                if(e.status!=409)throw e
                applySnapshot(withContext(Dispatchers.IO){client.snapshot()})
                error="Задача уже запущена или завершена. Отмена не выполнена."
                return@runWork
            }
            applySnapshot(withContext(Dispatchers.IO){client.snapshot()})
        }
    }
    private fun runWork(action:suspend ()->Unit){
        if(busy)return
        busy=true;error=null
        viewModelScope.launch {
            try{action()}catch(e:CancellationException){throw e}
            catch(e:Exception){
                stale=true
                if(e is ApiHttpException && e.status==401){val hadSession=connected;clearSession();error=if(hadSession)"Сеанс истёк или отозван. Подключитесь снова." else "Код недействителен, использован или истёк. Получите новый код."}
                else error=if(e is ApiHttpException)e.message else if(!connected)"Подключение не подтверждено. Код мог быть использован; получите новый код." else "Связь или формат ответа недоступны. Проверьте подключение."
            }
            finally{busy=false}
        }
    }
}
private val titles=listOf("Главная","Задачи","Чат","Настройки")
private fun statusLabel(value:String)=when(value){
    "ok"->"Работает";"degraded"->"Нестабильно";"failed"->"Ошибка";"unknown"->"Не проверено"
    "queued"->"В очереди";"running"->"Выполняется";"succeeded"->"Завершено";"needs_review"->"Требуется проверка"
    "disabled"->"Выключен";"cancelled"->"Отменено";else->value
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
    val scroll=rememberScrollState()
    val scope=rememberCoroutineScope()
    LaunchedEffect(page){scroll.scrollTo(0)}
    Column(modifier.fillMaxSize().verticalScroll(scroll).padding(16.dp),verticalArrangement=Arrangement.spacedBy(12.dp)){
        Row(verticalAlignment=Alignment.CenterVertically){
            Text(if(page==0)"PHANTOM CONTROL" else titles[page],style=MaterialTheme.typography.headlineSmall,modifier=Modifier.weight(1f))
            IconButton(onClick={s.refresh()},enabled=!s.busy && s.connected){Icon(Icons.Filled.Refresh,"Обновить")}
        }
        if(s.busy)LinearProgressIndicator(Modifier.fillMaxWidth())
        s.error?.let{Text(it,color=MaterialTheme.colorScheme.error)}
        if(s.stale)Text("Нет актуальных данных сервера",color=MaterialTheme.colorScheme.onSurfaceVariant)
        val snap=s.snapshot
        when(page){
            0 -> {
                if(snap==null){Text(if(s.connected)"Ожидание данных сервера." else "Подключите персональный сервер управления.");Button(onClick={if(s.connected)s.refresh() else navigate(3)},enabled=!s.busy){Text(if(s.connected)"Повторить" else "Подключение")}}
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
                    val isChat=page==2
                    val supportsHistory=snap?.features?.contains("chat_parent")==true
                    if(isChat && supportsHistory){
                        Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically){
                            Text(if(s.chatParent==null)"Без предыдущего контекста" else "Продолжение: "+s.chatParent!!.title.take(80),modifier=Modifier.weight(1f))
                            OutlinedButton(onClick={s.selectConversation(null)},enabled=!s.busy){Text("Новый диалог")}
                        }
                        Text("В контекст входят до шести предыдущих ответов выбранного диалога.",style=MaterialTheme.typography.bodySmall)
                        if(s.pendingChat!=null)Text("Ответ готовится. Можно начать новый диалог, не отменяя отправленный запрос.")
                    }
                    if(!isChat){
                        Text("Тип задачи")
                        available.forEach{c-> FilterChip(c.kind==s.kind,{s.kind=c.kind;s.model=c.models.firstOrNull()?:""},{Text(kindLabel(c.kind))},enabled=!s.busy)}
                    }
                    Text("Исполнитель")
                    selected.models.forEach{m-> FilterChip(m==s.model,{s.model=m},{Text(modelLabel(m))},enabled=!s.busy)}
                    val message=if(isChat)s.chatDraft else s.draft
                    OutlinedTextField(message,{if(isChat)s.chatDraft=it else s.draft=it},Modifier.fillMaxWidth(),label={Text(if(isChat)"Сообщение" else "Поручение")},minLines=3,enabled=!s.busy)
                    Button(onClick={s.submit(selected.kind,s.model)},enabled=!s.busy&&!s.stale&&message.isNotBlank()&&message.length<=4000&&s.model in selected.models&&(!isChat||s.pendingChat==null)){Text(if(isChat)"Отправить" else "Запустить")}
                }
                Text(if(page==2)"История диалогов" else "История задач",style=MaterialTheme.typography.titleLarge)
                val tasks=snap?.tasks.orEmpty().filter{if(page==2)it.kind=="chat" else it.kind!="chat"}
                if(tasks.isEmpty())Text("Задач нет.")
                tasks.forEach{t->
                    Card(Modifier.fillMaxWidth()){
                        Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(5.dp)){
                            Text(t.title,style=MaterialTheme.typography.titleMedium)
                            Text(statusLabel(t.state))
                            if(t.result.isNotBlank())Text(t.result)
                            if(t.kind=="chat" && t.parentId!=null)Text("Продолжение диалога",style=MaterialTheme.typography.bodySmall)
                            if(t.kind=="chat" && t.state=="succeeded" && snap?.features?.contains("chat_parent")==true)
                                TextButton(onClick={s.selectConversation(t);scope.launch{scroll.animateScrollTo(0)}},enabled=!s.busy&&!s.stale){Text("Продолжить")}
                            if(t.state=="queued" && snap?.features?.contains("cancel_queued")==true)
                                OutlinedButton(onClick={s.cancel(t)},enabled=!s.busy&&!s.stale){Text("Отменить")}
                            Text(t.id,style=MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }
            3 -> {
                Text("Сервер управления")
                OutlinedTextField(s.origin,{s.origin=it},Modifier.fillMaxWidth(),label={Text("HTTPS-адрес")},singleLine=true,enabled=!s.busy&&!s.connected)
                if(!s.connected) OutlinedTextField(s.pairingCode,{s.pairingCode=it},Modifier.fillMaxWidth(),label={Text("Одноразовый код")},singleLine=true,visualTransformation=PasswordVisualTransformation(),enabled=!s.busy)
                Text(if(s.connected)"Сеанс активен. Срок действия до 12 часов." else "Код действует 10 минут. Получите его через доверенный канал владельца.")
                Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){
                    Button(onClick={s.connect()},enabled=!s.busy&&!s.connected){Text("Подключить")}
                    OutlinedButton(onClick={s.disconnect()},enabled=!s.busy&&s.connected){Text("Выйти")}
                }
                Text("Тема оформления",style=MaterialTheme.typography.titleLarge)
                listOf("auto" to "Авто","graphite" to "Графит","navy" to "Тёмно-синяя","light" to "Светлая").forEach{(key,label)->FilterChip(theme==key,{onTheme(key)},{Text(label)})}
            }
        }
    }
}
