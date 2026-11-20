"""On-device entry points. ASGI requests stay in-process: no listening port."""
import asyncio
import json
import os
from pathlib import Path

_app = None
_monitor = None


def initialize(files_dir, library_path, default_source='public'):
    global _app, _monitor
    if _app is not None:
        return True
    os.environ['MONITOR_RUNTIME'] = 'android'
    os.environ['MONITOR_DB'] = str(Path(files_dir) / 'monitor.sqlite3')
    os.environ['MONITOR_TALIB_LIBRARY'] = library_path
    from . import storage
    fresh = not Path(os.environ['MONITOR_DB']).exists()
    storage.initialize()
    if fresh:
        with storage.connect() as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', ('source', json.dumps(default_source)))
    from .main import app, monitor
    _app, _monitor = app, monitor
    return True


def configure(credentials):
    values = json.loads(credentials)
    for key in ('TUSHARE_TOKEN', 'SMTP_HOST', 'SMTP_PORT', 'SMTP_USER', 'SMTP_PASSWORD', 'SMTP_FROM', 'ALERT_EMAIL'):
        value = values.get(key, '')
        if not isinstance(value, str) or len(value) > 2048:
            raise ValueError('Invalid credential configuration')
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)


def request(method, path, body=''):
    if (_app is None or method not in ('GET', 'POST', 'PUT', 'DELETE')
            or not path.startswith('/api/') or len(path) > 8192 or len(body) > 128 * 1024):
        return json.dumps({'status': 400, 'body': {'detail': '无效的本地请求'}})
    async def execute():
        import httpx
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app), base_url='http://localhost') as client:
            result = await client.request(method, path, content=body.encode(), headers={'Content-Type': 'application/json'})
            return json.dumps({'status': result.status_code, 'body': result.json()}, ensure_ascii=False, allow_nan=False)
    try:
        return asyncio.run(execute())
    except Exception:
        return json.dumps({'status': 500, 'body': {'detail': '手机本地请求失败，请重试或查看运行状态'}})


def tick():
    from . import storage
    try:
        completed = _monitor.tick()
        return json.dumps({'ok': completed, 'interval': storage.settings()['interval'],
                           'session': _monitor.session(), 'last_sync': _monitor.last_sync}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({'ok': False, 'interval': 60, 'error': str(exc)[:160]}, ensure_ascii=False)


def notifications(after_id):
    from . import storage
    return json.dumps(storage.rows('SELECT id,rule_name,name,symbol,source,bar_time FROM alerts WHERE id>? ORDER BY id LIMIT 50', (int(after_id),)), ensure_ascii=False)
