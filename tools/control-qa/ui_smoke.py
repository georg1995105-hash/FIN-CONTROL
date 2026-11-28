"""Drive actual Compose screens on Android. All data and CA are synthetic."""
import pathlib
import re
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from fixture import Fixture

PKG='pro.veor.phantomcontrol'
OUT=pathlib.Path('control-qa-evidence')
OUT.mkdir(exist_ok=True)

def adb(*args,timeout=25):
    p=subprocess.run(['adb',*args],capture_output=True,timeout=timeout,check=True)
    return p.stdout

def dump():
    adb('shell','uiautomator','dump','/sdcard/control-qa.xml',timeout=20)
    return ET.fromstring(adb('shell','cat','/sdcard/control-qa.xml'))

def node(text,limit=35):
    deadline=time.monotonic()+limit
    while time.monotonic()<deadline:
        try:
            for n in dump().iter('node'):
                if n.get('text')==text or n.get('content-desc')==text:
                    return n
        except (subprocess.SubprocessError,ET.ParseError):pass
        time.sleep(.5)
    raise AssertionError('Visible element not found: '+text)

def tap(text):
    n=node(text)
    x1,y1,x2,y2=map(int,re.findall(r'\d+',n.get('bounds')))
    adb('shell','input','tap',str((x1+x2)//2),str((y1+y2)//2))
    time.sleep(.4)

def enter(label,value):
    tap(label)
    adb('shell','input','text',value)
    info=adb('shell','dumpsys','input_method').decode(errors='replace')
    if 'mInputShown=true' in info:
        adb('shell','input','keyevent','4')
    time.sleep(.4)

def screenshot(name):
    (OUT/(name+'.png')).write_bytes(adb('exec-out','screencap','-p'))

def start():
    adb('shell','am','start','-W','-n',PKG+'/.MainActivity')
    time.sleep(1)

server=Fixture(sys.argv[1],sys.argv[2])
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
try:
    adb('install','-r',sys.argv[3],timeout=120)
    adb('shell','settings','put','secure','show_ime_with_hard_keyboard','0')
    adb('shell','input','keyevent','82')
    start()
    node('Подключите персональный сервер управления.')
    tap('Подключение')
    enter('HTTPS-адрес','https://10.0.2.2:38443')
    enter('Одноразовый код','A'*43)
    tap('Подключить')
    node('Код недействителен, использован или истёк. Получите новый код.')
    enter('Одноразовый код',server.issue())
    tap('Подключить')
    node('Сеанс активен. Срок действия до 12 часов.')
    tap('Главная')
    node('Тест платежей');node('Ошибка');node('Автопилот: Выключен')
    screenshot('01-home-failure')
    tap('Задачи')
    node('Штатная диагностика')
    enter('Поручение','qa_readonly')
    tap('Запустить')
    node('qa_readonly');node('Завершено',45)
    node('Диагностика выполнена без изменений')
    screenshot('02-task-result')
    adb('shell','input','keyevent','3');time.sleep(2);start()
    node('qa_readonly')
    with server.lock:
        assert len(server.tasks)==1
    tap('Настройки');tap('Выйти')
    node('Одноразовый код')
    with server.lock:
        assert server.token is None and len(server.tasks)==1
    enter('Одноразовый код',server.issue());tap('Подключить')
    node('Сеанс активен. Срок действия до 12 часов.')
    tap('Задачи');node('qa_readonly')
    with server.lock:server.token=None
    tap('Обновить')
    node('Сеанс истёк или отозван. Подключитесь снова.')
    tap('Настройки');node('Одноразовый код')
    screenshot('03-revoked')
    adb('shell','am','force-stop',PKG);start()
    node('Подключите персональный сервер управления.')
    (OUT/'result.txt').write_text('PASS: actual Android UI; invalid code, HTTPS enrollment, failed service state, task execution contract, background return, logout/re-enrollment, preserved task, remote revocation, process restart.\n')
    print((OUT/'result.txt').read_text())
finally:
    server.shutdown();thread.join();server.server_close()
