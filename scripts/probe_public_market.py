"""Read-only connectivity probe. No credentials, no database mutations."""
import concurrent.futures
import json
import time
import sys

import httpx

URLS = {
    'eastmoney_stock': 'https://push2his.eastmoney.com/api/qt/stock/trends2/get?secid=1.600519&fields1=f1,f2,f3,f4,f5,f6,f7,f8&fields2=f51,f52,f53,f54,f55,f56,f57,f58&ndays=5&iscr=0',
    'eastmoney_etf': 'https://push2his.eastmoney.com/api/qt/stock/trends2/get?secid=1.510300&fields1=f1,f2,f3,f4,f5,f6,f7,f8&fields2=f51,f52,f53,f54,f55,f56,f57,f58&ndays=5&iscr=0',
    'sina_stock': 'https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_data=/CN_MarketDataService.getKLineData?symbol=sh600519&scale=1&ma=no&datalen=1970',
    'sina_etf': 'https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_data=/CN_MarketDataService.getKLineData?symbol=sh510300&scale=60&ma=no&datalen=1970',
    'tencent_stock': 'https://web.ifzq.gtimg.cn/appstock/app/kline/mkline?param=sh600519,m1,,1000',
    'tencent_etf': 'https://web.ifzq.gtimg.cn/appstock/app/kline/mkline?param=sh510300,m1,,1000',
    'tencent_daily': 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh510300,day,,,640,',
    'calendar': 'https://finance.sina.com.cn/realstock/company/klc_td_sh.txt',
}

def probe(item):
    label, url = item
    start = time.monotonic()
    try:
        r = httpx.get(url, timeout=15, follow_redirects=True, trust_env='--direct' not in sys.argv,
                     headers={'User-Agent':'Mozilla/5.0','Referer':'https://finance.sina.com.cn/'})
        text = r.text
        return {'name':label,'seconds':round(time.monotonic()-start,1),'status':r.status_code,'length':len(text),'head':text[:320],'tail':text[-380:]}
    except Exception as exc:
        return {'name':label,'error':type(exc).__name__+': '+str(exc)[:180]}

if __name__ == '__main__':
    if '--adapter' in sys.argv:
        import os
        import tempfile
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from backend import storage, indicators
        from backend.public_market import PublicProvider
        from backend.market import TIMEFRAMES
        from backend.service import Monitor
        with tempfile.TemporaryDirectory(prefix='market-probe-') as folder:
            os.environ['MONITOR_DB'] = str(Path(folder)/'probe.sqlite3')
            storage.initialize()
            provider = PublicProvider()
            for symbol in ['510300.SH','159915.SZ','588000.SH','600519.SH','300750.SZ','601318.SH']:
                start = time.monotonic()
                data = provider.fetch(symbol)
                checks = {}
                for tf in TIMEFRAMES:
                    bars = data.bars(tf)
                    macd = indicators.calculate(bars, 'MACD')
                    checks[tf] = {'bars':len(bars),'valid':int(bars['close'].count()),'macd_ready':bool(len(macd) and macd.iloc[-1].notna().all())}
                print(json.dumps({'symbol':symbol,'seconds':round(time.monotonic()-start,1),'latest':str(data.minute.index[-1]),'close':float(data.minute.iloc[-1]['close']),'current':Monitor().current(data),'issues':data.issues,'periods':checks}, ensure_ascii=False),flush=True)
        sys.exit(0)
    if '--extended' in sys.argv:
        URLS = {
            'em_1m': 'https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.510300&klt=1&fqt=0&beg=0&end=20500101&lmt=2000&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
            'em_5m': 'https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.510300&klt=5&fqt=0&beg=0&end=20500101&lmt=2000&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
            'em_daily': 'https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.510300&klt=101&fqt=0&beg=20140101&end=20500101&lmt=4000&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
            'sina_daily': 'https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_data=/CN_MarketDataService.getKLineData?symbol=sh510300&scale=240&ma=no&datalen=1970',
        }
    if '--calendar' in sys.argv:
        import akshare as ak
        calendar = ak.tool_trade_date_hist_sina()
        print(calendar.tail(10).to_json(orient='records', date_format='iso'), flush=True)
        sys.exit(0)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(probe, URLS.items()):
            print(json.dumps(result, ensure_ascii=False), flush=True)
