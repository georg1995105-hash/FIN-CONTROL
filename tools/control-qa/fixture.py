"""Synthetic v1 contract fixture only; no real services or credentials."""
import datetime as dt
import hmac
import json
import secrets
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class Fixture(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,cert,key):
        super().__init__(('127.0.0.1',38443),Handler)
        self.lock=threading.Lock();self.code=None;self.token=None;self.tasks={}
        tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.minimum_version=ssl.TLSVersion.TLSv1_2
        tls.load_cert_chain(cert,key)
        self.socket=tls.wrap_socket(self.socket,server_side=True)
    def issue(self):
        with self.lock:
            self.code=secrets.token_urlsafe(32)
            return self.code

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def respond(self,status,payload):
        b=json.dumps(payload,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    def authorized(self):
        token=self.server.token
        return token is not None and hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token)
    def do_GET(self):
        with self.server.lock:
            if not self.authorized():return self.respond(401,{'error':'Unauthorized'})
            if self.path=='/v1/status':
                return self.respond(200,{'version':1,'observed_at':dt.datetime.now(dt.timezone.utc).isoformat(),'autopilot':'disabled','features':['chat_parent','cancel_queued'],'services':[{'name':'Тест платежей','state':'failed','detail':'Синтетический отказ'}],'capabilities':[{'kind':'diagnose','models':['local-readonly']},{'kind':'chat','models':['fixture-chat/high','fixture-chat/medium']}]})
            if self.path=='/v1/tasks':
                now=time.monotonic();items=[]
                for task in self.server.tasks.values():
                    r={k:v for k,v in task.items() if k!='due'}
                    if task['state']!='cancelled' and now>=task['due']:r.update(state='succeeded',result='Тестовый ответ' if task['kind']=='chat' else 'Диагностика выполнена без изменений')
                    items.append(r)
                return self.respond(200,{'tasks':items})
            return self.respond(404,{})
    def do_POST(self):
        try:
            n=int(self.headers.get('Content-Length','0'));assert 0<n<=24576
            b=json.loads(self.rfile.read(n));assert isinstance(b,dict)
        except (ValueError,TypeError,AssertionError):return self.respond(400,{})
        with self.server.lock:
            if self.path=='/v1/session':
                if self.server.code is None or b!={'code':self.server.code}:return self.respond(401,{})
                self.server.code=None;self.server.token=secrets.token_urlsafe(32)
                return self.respond(200,{'token':self.server.token,'expires_in':43200})
            if not self.authorized():return self.respond(401,{})
            if self.path=='/v1/session/revoke':
                self.server.token=None;return self.respond(200,{'revoked':True})
            if self.path=='/v1/tasks/cancel':
                task=self.server.tasks.get(b.get('id'))
                if not task or task['state'] not in ('queued','cancelled'):return self.respond(409,{})
                task.update(state='cancelled',result='Cancelled before execution.')
                return self.respond(200,{'state':'cancelled'})
            if self.path=='/v1/tasks':
                required={'request_id','kind','model','title'}
                if not required<=set(b) or set(b)-required-{'parent_id'}:return self.respond(400,{})
                caps={'diagnose':['local-readonly'],'chat':['fixture-chat/high','fixture-chat/medium']}
                if b['model'] not in caps.get(b['kind'],[]):return self.respond(400,{})
                parent=b.get('parent_id')
                if parent is not None:
                    previous=self.server.tasks.get(parent)
                    if b['kind']!='chat' or not previous or previous['kind']!='chat' or previous['state']=='cancelled' or time.monotonic()<previous['due']:
                        return self.respond(400,{})
                ident=b['request_id'];queued=b['title']=='qa_cancel'
                task={'id':ident,'kind':b['kind'],'model':b['model'],'parent_id':parent,'state':'queued' if queued else 'running','title':b['title'],'result':'','due':time.monotonic()+(3600 if queued else 2)}
                old=self.server.tasks.get(ident)
                if old and any(old[k]!=task[k] for k in ('kind','model','parent_id','title')):return self.respond(409,{})
                self.server.tasks.setdefault(ident,task)
                return self.respond(200,{'id':ident})
            return self.respond(404,{})
