"""Opt-in, authenticated LAN gateway to the existing loopback monitor.

One backend owns scheduling and SQLite. This process only proxies the same UI/API.
"""
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response

ROOT = Path(__file__).resolve().parent.parent
COOKIE = 'guanlan_session'
SESSION_SECONDS = 30 * 86400
MAX_BODY = 128 * 1024


def load_env():
    if (ROOT / '.env').exists():
        for line in (ROOT / '.env').read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('\"\''))


def access_key():
    path = Path(os.getenv('MONITOR_MOBILE_KEY_FILE', ROOT / 'data/mobile-key.secret'))
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        key = path.read_text().strip()
    else:
        key = secrets.token_urlsafe(24)
        with os.fdopen(fd, 'w') as file:
            file.write(key + '\n')
    if len(key) < 32:
        raise ValueError('手机配对码文件无效，至少需要 32 个字符')
    path.chmod(0o600)
    return key


def session_token(key, expires=None):
    payload = f'{int(time.time()) + SESSION_SECONDS if expires is None else expires}.{secrets.token_hex(12)}'
    signature = hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f'{payload}.{signature}'


def valid_session(key, token):
    try:
        if len(token) > 160:
            return False
        expires, nonce, signature = token.split('.')
        expected = hmac.new(key.encode(), f'{expires}.{nonce}'.encode(), hashlib.sha256).hexdigest()
        return int(expires) > time.time() and hmac.compare_digest(signature, expected)
    except (ValueError, TypeError, AttributeError):
        return False


def allowed_host(host):
    if host == 'localhost':
        return True
    if host in os.getenv('MONITOR_MOBILE_HOSTS', '').split(','):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback or ip in ipaddress.ip_network('10.0.0.0/8') or ip in ipaddress.ip_network('172.16.0.0/12') or ip in ipaddress.ip_network('192.168.0.0/16')
    except (ValueError, TypeError):
        return False


def lan_addresses():
    addresses = set()
    try:
        addresses.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(('8.8.8.8', 80))  # Routing lookup; no packet is sent.
            addresses.add(sock.getsockname()[0])
    except OSError:
        pass
    return sorted(x for x in addresses if allowed_host(x) and not x.startswith('127.'))


CONNECT_HTML = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>连接观澜</title>
<style>body{margin:0;background:#f4f6f7;color:#24383b;font:16px system-ui;padding:28px;line-height:1.7}
main{max-width:420px;margin:10vh auto}b{background:#234c42;color:white;border-radius:16px;padding:14px;font-size:26px}
h1{margin-top:30px}p{color:#68797e}label{display:block}input,button{box-sizing:border-box;width:100%;font:inherit;padding:14px;border-radius:10px;margin:10px 0;border:1px solid #d1ddda}
button{background:#234c42;color:white;border:0}#error{color:#aa3939;min-height:30px}small{color:#71827d}</style>
<main><b>观</b><h1>连接你的监控工作空间</h1><p>输入电脑启动手机连接服务时显示的配对码。自选、规则与报警将与电脑网页同步。</p>
<form id="pair"><label for="key">配对码</label><input id="key" name="key" type="password" autocomplete="current-password" required maxlength="128" placeholder="粘贴电脑上的配对码">
<button id="submit">验证并进入</button><div id="error" role="alert"></div></form>
<small>仅在可信 Wi-Fi 中使用本地 HTTP 连接。电脑与监控服务需要保持运行；连接有效期为 30 天。</small><p><a href="/download/guanlan.apk">下载 Android 安装包</a></p></main>
<script>document.querySelector('#pair').addEventListener('submit',async e=>{e.preventDefault();const b=document.querySelector('#submit'),o=document.querySelector('#error');b.disabled=true;o.textContent='';try{const r=await fetch('/connect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:document.querySelector('#key').value.trim()})});const j=await r.json();if(!r.ok)throw Error(j.detail);location.replace('/');}catch(e){o.textContent=e.message||'连接失败，请重试';}finally{b.disabled=false;}});</script></html>'''


def create_app(key=None, upstream=None, manage_backend=False):
    load_env()
    key = key or access_key()
    upstream = upstream or f"http://127.0.0.1:{int(os.getenv('MONITOR_PORT', '8787'))}"
    attempts = OrderedDict()

    @asynccontextmanager
    async def lifespan(app):
        process = None
        async with httpx.AsyncClient(base_url=upstream, timeout=90, trust_env=False, follow_redirects=False) as client:
            app.state.client = client
            if manage_backend:
                try:
                    probe = await client.get('/api/status', timeout=3)
                    if probe.status_code != 200 or 'indicator_count' not in probe.json():
                        raise RuntimeError('后端端口已被其他服务占用')
                except httpx.ConnectError:
                    process = subprocess.Popen([sys.executable, '-m', 'backend'], cwd=ROOT)
            try:
                yield
            finally:
                if process is not None and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware('http')
    async def gate(request: Request, call_next):
        if not allowed_host(request.url.hostname):
            return JSONResponse({'detail': '不允许的服务地址'}, status_code=400)
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('origin')
            expected = f"{request.url.scheme}://{request.headers.get('host')}"
            if origin and origin != expected:
                return JSONResponse({'detail': '仅允许同源请求'}, status_code=403)
            # Block form-based CSRF even when an Origin header is absent.
            if request.method == 'POST' and request.headers.get('content-type', '').split(';')[0] != 'application/json':
                return JSONResponse({'detail': '请求必须为 JSON'}, status_code=415)
        if request.url.path not in ('/connect', '/download/guanlan.apk') and not valid_session(key, request.cookies.get(COOKIE)):
            if request.method == 'GET' and 'text/html' in request.headers.get('accept', ''):
                response = RedirectResponse('/connect', status_code=303)
            else:
                response = JSONResponse({'detail': '连接已过期，请在 App 中刷新并重新配对'}, status_code=401)
        else:
            response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        return response

    async def body_bytes(request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_BODY:
                return None
        return bytes(body)

    @app.get('/connect')
    def connect_page():
        return HTMLResponse(CONNECT_HTML)

    @app.get('/download/guanlan.apk')
    def download_apk():
        apk = ROOT / 'dist/android/guanlan-0.3.1.apk'
        if not apk.is_file():
            return JSONResponse({'detail': 'APK 尚未打包完成'}, status_code=404)
        return FileResponse(apk, media_type='application/vnd.android.package-archive', filename=apk.name)

    @app.post('/connect')
    async def pair(request: Request):
        client = request.client.host if request.client else 'unknown'
        stamp = time.monotonic()
        times = [t for t in attempts.get(client, []) if stamp - t < 60]
        if len(times) >= 5:
            return JSONResponse({'detail': '尝试次数过多，请一分钟后重试'}, status_code=429, headers={'Retry-After': '60'})
        body = await body_bytes(request)
        if body is None:
            return JSONResponse({'detail': '请求过大'}, status_code=413)
        try:
            candidate = json.loads(body).get('key', '')
            accepted = isinstance(candidate, str) and hmac.compare_digest(candidate.encode(), key.encode())
        except (ValueError, AttributeError):
            accepted = False
        if not accepted:
            attempts[client] = times + [stamp]
            attempts.move_to_end(client)
            while len(attempts) > 2048:
                attempts.popitem(last=False)
            return JSONResponse({'detail': '配对码不正确'}, status_code=401)
        attempts.pop(client, None)
        response = JSONResponse({'ok': True})
        response.set_cookie(COOKIE, session_token(key), max_age=SESSION_SECONDS,
                            httponly=True, secure=request.url.scheme == 'https', samesite='strict')
        return response

    @app.post('/disconnect')
    def disconnect():
        response = JSONResponse({'ok': True})
        response.delete_cookie(COOKIE)
        return response

    @app.api_route('/{path:path}', methods=['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE'])
    async def proxy(path: str, request: Request):
        body = await body_bytes(request)
        if body is None:
            return JSONResponse({'detail': '请求过大'}, status_code=413)
        # A fixed destination, a fixed Host, no incoming cookies or proxy headers.
        # Copy raw_path via URL.copy_with so //host cannot become a proxy target.
        url = httpx.URL(upstream).copy_with(raw_path=request.scope['raw_path'] + (b'?' + request.scope['query_string'] if request.scope['query_string'] else b''))
        headers = {name: request.headers[name] for name in ('content-type', 'accept') if name in request.headers}
        try:
            result = await app.state.client.request(request.method, url, content=body, headers=headers)
        except httpx.HTTPError:
            return JSONResponse({'detail': '电脑监控服务暂未就绪，请稍后刷新'}, status_code=503)
        headers = {k: v for k, v in result.headers.items() if k.lower() not in
                   ('content-length', 'content-encoding', 'transfer-encoding', 'connection', 'set-cookie')}
        location = headers.get('location', '')
        if location.startswith(upstream + '/'):
            headers['location'] = location[len(upstream):]
        return Response(result.content, status_code=result.status_code, headers=headers)

    return app


if __name__ == '__main__':
    load_env()
    key = access_key()
    port = int(os.getenv('MONITOR_MOBILE_PORT', '8788'))
    print('\n观澜 · 手机连接（请与电脑连接同一个可信 Wi-Fi）', flush=True)
    for address in lan_addresses():
        print(f'服务地址：http://{address}:{port}', flush=True)
    print(f'配对码：{key}\n关闭此窗口将断开手机连接。\n', flush=True)
    uvicorn.run(create_app(key=key, manage_backend=True), host='0.0.0.0', port=port, proxy_headers=False)
