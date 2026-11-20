"""Optional real HTTPS adapter probe. Kept separate from deterministic tests."""
import json
import os
import tempfile
import httpx
from backend import storage, indicators
from backend.public_market import PublicProvider
from backend.service import Monitor
original = os.environ['MONITOR_DB']
with tempfile.TemporaryDirectory() as temporary:
    os.environ['MONITOR_DB'] = temporary + '/network.sqlite3'
    try:
        storage.initialize()
        diagnostics = []
        for url in ['https://finance.sina.com.cn/realstock/company/klc_td_sh.txt', 'https://push2his.eastmoney.com/api/qt/stock/kline/get']:
            try:
                response = httpx.get(url, timeout=10)
                diagnostics.append({'host':httpx.URL(url).host,'status':response.status_code})
            except Exception as exc:
                diagnostics.append({'host':httpx.URL(url).host,'error':repr(exc)})
        results = []
        for symbol in ['510300.SH', '600519.SH']:
            data = PublicProvider().fetch(symbol)
            macd = indicators.calculate(data.daily, 'MACD')
            results.append({'symbol':symbol,'source':data.source,'minute_rows':len(data.minute),'daily_rows':len(data.daily),
                'providers':data.providers,'current':Monitor().current(data),'daily_macd_ready':bool(macd.iloc[-1].notna().all()),
                'issues':data.issues,'minute_time':str(data.minute.index[-1]),'close':float(data.minute.iloc[-1]['close'])})
        RESULT = json.dumps({'results':results,'network':diagnostics},ensure_ascii=False)
    except Exception as exc:
        RESULT = json.dumps({'error':str(exc),'network':diagnostics},ensure_ascii=False)
    finally:
        os.environ['MONITOR_DB'] = original
