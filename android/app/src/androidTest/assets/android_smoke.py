"""Instrumentation only: temporary database, deterministic data, no production hooks."""
import json
import os
import tempfile
from unittest.mock import patch

from backend import android_runtime as runtime, indicators, storage
from backend.market import DemoProvider, TIMEFRAMES
import pandas as pd

original = os.environ['MONITOR_DB']
with tempfile.TemporaryDirectory() as temporary:
    os.environ['MONITOR_DB'] = temporary + '/smoke.sqlite3'
    try:
        storage.initialize()
        clock = pd.Timestamp('2026-11-06 14:37')
        data = DemoProvider().fetch('510300.SH', clock)
        for name, spec in indicators.CATALOG.items():
            if spec['available']:
                frame = data.minute if name == 'VWAP' else data.daily
                values = indicators.series(frame, name)
                assert len(values) == len(frame), name
        for tf in TIMEFRAMES:
            assert len(data.bars(tf)), tf
        def request(method, path, body=None):
            result = json.loads(runtime.request(method, '/api' + path, '' if body is None else json.dumps(body)))
            assert result['status'] == 200, result
            return result['body']
        assert request('GET', '/status')['runtime'] == 'android'
        request('PUT', '/settings', {'source':'demo','interval':60})
        rule = request('POST','/rules',{'name':'手机独立验证','expression':'RSI(14) >= 0','symbols':['510300.SH'],'enabled':True})
        with patch('backend.service.now', return_value=clock), patch('backend.main.now', return_value=clock):
            runtime._monitor.cache.clear()
            with patch.object(runtime._monitor,'market', return_value=data):
                assert request('GET','/watchlist')[0]['price'] is not None
                assert request('GET','/chart?symbol=510300.SH&tf=15m&indicator=MACD')
                assert request('POST','/scan',{'expression':'RSI(14) >= 0','symbols':['510300.SH']})['matched'] == 1
                runtime.tick()
                rows = request('GET','/alerts')
                assert any(r['rule_name']=='手机独立验证' for r in rows)
                count = len(rows)
                runtime.tick()
                assert len(request('GET','/alerts')) == count  # No duplicate sustained alerts.
                assert json.loads(runtime.notifications(0))
        exported = request('GET','/workspace/export')
        assert request('POST','/workspace/import', exported)['rules_added'] == 0
        assert request('GET','/rules')  # Fresh SQLite connection proves persistence.
        assert json.loads(runtime.request('GET','https://example.test'))['status'] == 400
    finally:
        os.environ['MONITOR_DB'] = original
        runtime._monitor.cache.clear()
        runtime._monitor.screen_cache = None
SUCCESS = True
