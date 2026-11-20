#!/usr/bin/env python3
"""Read-only live connection check. Does not create rules, alerts or watch items."""
import json
import sys
from pathlib import Path

import httpx

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from backend.mobile import access_key, load_env

load_env()
base = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8788'
with httpx.Client(base_url=base, timeout=90, trust_env=False) as client:
    assert client.get('/api/status').status_code == 401
    response = client.post('/connect', json={'key': access_key()})
    response.raise_for_status()
    status = client.get('/api/status').json()
    watch = client.get('/api/watchlist').json()
    rules = client.get('/api/rules').json()
    screen = client.get('/api/rule-screen')
    screen.raise_for_status()
    script = client.get('/app.js')
    script.raise_for_status()
    assert script.headers['cache-control'] == 'no-store'
    assert script.content == (root / 'web/app.js').read_bytes()
    print(json.dumps({'gateway': base, 'source': status['source'], 'watch_count': len(watch),
                      'rule_count': len(rules), 'screen_ok': True, 'shared_web_verified': True}, ensure_ascii=False))
