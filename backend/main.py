import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import indicators, storage
from .market import INSTRUMENTS, TIMEFRAMES, instrument, now
from .rules import Evaluator, parse
from .service import Monitor

ROOT = Path(__file__).resolve().parent.parent
if (ROOT/'.env').exists():
    for raw in (ROOT/'.env').read_text().splitlines():
        raw=raw.strip()
        if raw and not raw.startswith('#') and '=' in raw:
            key,val=raw.split('=',1)
            os.environ.setdefault(key.strip(),val.strip().strip('\"\''))

monitor=Monitor()
LIST_LIMIT = {'max_length': 200} if hasattr(BaseModel, 'model_dump') else {'max_items': 200}


@asynccontextmanager
async def lifespan(app):
    storage.initialize()
    if not os.getenv('MONITOR_TEST'): monitor.start()
    yield
    monitor.close()


app=FastAPI(title='观澜 · A股监控',version='0.1.0',lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['localhost','127.0.0.1','[::1]','testserver'])


@app.middleware('http')
async def same_origin(request: Request, call_next):
    if request.method not in ['GET','HEAD','OPTIONS']:
        origin=request.headers.get('origin')
        if origin and origin != f"{request.url.scheme}://{request.headers.get('host')}":
            return JSONResponse({'detail':'仅允许本地同源请求'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    if request.url.path.startswith('/api'): response.headers['Cache-Control']='no-store'
    return response


@app.exception_handler(ValueError)
async def value_error(request, exc):
    return JSONResponse({'detail':str(exc)},status_code=400)


def finite(val):
    return float(val) if val is not None and np.isfinite(val) else None


def get_market(symbol):
    try:
        return monitor.market(instrument(symbol)['symbol'])
    except ValueError: raise
    except Exception:
        raise HTTPException(503,'行情加载失败，请检查数据源配置') from None


@app.get('/api/status')
def status():
    config=storage.settings()
    return {'source':config['source'],'interval':config['interval'],'last_sync':monitor.last_sync,
            'session':monitor.session(),
            'server_time':str(now()),'errors':dict(monitor.errors),
            'indicator_count':sum(x['available'] for x in indicators.CATALOG.values()),
            'watch_count':storage.rows('SELECT COUNT(*) AS n FROM watchlist')[0]['n'],
            'rule_count':storage.rows('SELECT COUNT(*) AS n FROM rules WHERE enabled=1')[0]['n'],
            'unread':storage.rows('SELECT COUNT(*) AS n FROM alerts WHERE read=0')[0]['n'],
            'email_configured':all(os.getenv(x) for x in ['SMTP_HOST','SMTP_FROM','ALERT_EMAIL']),
            'tushare_configured':bool(os.getenv('TUSHARE_TOKEN')), 'timeframes':TIMEFRAMES,
            'price_mode':'不复权', 'demo_calendar':'演示仅按工作日生成，不含真实节假日',
            'runtime':os.getenv('MONITOR_RUNTIME', 'desktop')}


@app.get('/api/instruments')
def search(q: str=''):
    result=[dict(zip(['symbol','name','kind'],x[:3])) for x in INSTRUMENTS if q.lower() in (x[0]+x[1]).lower()]
    if not result and q.strip():
        try: result=[{**instrument(q),'unverified':True}]
        except ValueError: pass
    return result[:30]


@app.get('/api/watchlist')
def watchlist():
    result=[]
    for item in storage.rows('SELECT * FROM watchlist ORDER BY added_at,symbol'):
        try:
            market=get_market(item['symbol'])
            minute,daily=market.minute,market.daily
            valid = minute.dropna(subset=['close'])
            if valid.empty: valid = daily.dropna(subset=['close'])
            if valid.empty: raise ValueError('暂无有效价格，等待行情更新')
            stamp=valid.index[-1]
            price=float(valid['close'].iloc[-1])
            prev=daily[daily.index.normalize()<stamp.normalize()]['close'].dropna()
            previous=prev.iloc[-1] if len(prev) else None
            today=minute[minute.index.normalize()==stamp.normalize()]
            complete_day=daily[daily.index.normalize()==stamp.normalize()]
            turnover=complete_day['amount'].iloc[-1] if len(complete_day) else today['amount'].sum(min_count=len(today)) if len(today) else None
            rsi=indicators.series(daily,'RSI',(14,)).iloc[-1] if len(daily) else None
            item.update(price=price,change=finite((price/previous-1)*100) if previous else None, rsi=finite(rsi),
                        amount=finite(turnover),sparkline=[finite(v) for v in daily['close'].tail(28)],
                        time=str(stamp),stale=not monitor.current(market),source=market.source,
                        warning='；'.join(market.issues))
        except Exception as exc:
            item.update(error=str(exc)[:180],price=None,change=None,rsi=None,amount=None,sparkline=[])
        result.append(item)
    return result


class WatchInput(BaseModel):
    symbol: str = Field(max_length=20)


@app.post('/api/watchlist')
def add_watch(body:WatchInput):
    item=instrument(body.symbol)
    if storage.rows('SELECT COUNT(*) AS n FROM watchlist')[0]['n']>=200:
        raise ValueError('本地版最多支持 200 个自选标的')
    with monitor.lock, storage.connect() as db:
        db.execute('INSERT OR IGNORE INTO watchlist(symbol,name,kind) VALUES(?,?,?)',(item['symbol'],item['name'],item['kind']))
    return item


@app.delete('/api/watchlist/{symbol}')
def remove_watch(symbol:str):
    with monitor.lock, storage.connect() as db:
        db.execute('DELETE FROM watchlist WHERE symbol=?',(symbol,))
        db.execute('DELETE FROM rule_state WHERE symbol=?',(symbol,))
    return {'ok':True}


@app.get('/api/indicators')
def get_indicators():
    return list(indicators.CATALOG.values())


@app.get('/api/chart')
def chart(symbol:str,tf:str='1d',indicator:str='MACD',params:str='{}'):
    market=get_market(symbol)
    bars=market.bars(tf)
    try: parameters=json.loads(params)
    except ValueError: raise ValueError('指标参数需为 JSON 对象') from None
    if not isinstance(parameters,dict): raise ValueError('指标参数需为 JSON 对象')
    outputs=indicators.calculate(bars,indicator,kwargs=parameters)
    boll=indicators.calculate(bars,'BBANDS',kwargs={'timeperiod':20})
    selected=bars.tail(100)
    values=[]
    for stamp,row in selected.iterrows():
        values.append({'time':str(stamp),**{key:finite(v) for key,v in row.items()},
                       'boll':{key:finite(v) for key,v in boll.loc[stamp].items()},
                       'indicator':{key:finite(v) for key,v in outputs.loc[stamp].items()}})
    return {'symbol':symbol,'tf':tf,'source':market.source,'bars':values,'indicator':indicator,
            'outputs':list(outputs.columns),'asof':str(market.asof),'price_mode':'不复权',
            'closed_only':True,'stale':not monitor.current(market), 'warnings':market.issues,
            'providers': market.providers,
            'amount_missing': bool(len(bars) and not np.isfinite(bars['amount'].iloc[-1])),
            'history_count':len(bars), 'valid_count':int(bars['close'].notna().sum())}


class RuleInput(BaseModel):
    name: str=Field(min_length=1,max_length=80)
    expression: str=Field(min_length=1,max_length=4000)
    symbols: list[str]=Field(default_factory=list,**LIST_LIMIT)
    enabled: bool=True


def validate_rule(body, allowed_symbols=None):
    if not body.name.strip() or any(ord(c)<32 for c in body.name):
        raise ValueError('规则名称不能为空或含换行控制符')
    parse(body.expression)
    body.symbols=list(dict.fromkeys(instrument(s)['symbol'] for s in body.symbols))
    watch = allowed_symbols if allowed_symbols is not None else {x['symbol'] for x in storage.rows('SELECT symbol FROM watchlist')}
    if any(s not in watch for s in body.symbols):
        raise ValueError('指定规则的标的需要先加入自选列表')
    # A deterministic sandbox validates types/arguments even without live credentials.
    from .market import DemoProvider
    Evaluator(DemoProvider().fetch('510300.SH')).run(body.expression)
    return body


@app.get('/api/rules')
def get_rules(symbol:str|None=None):
    rules=storage.rules()
    if symbol:
        symbol=instrument(symbol)['symbol']
        rules=[r for r in rules if not r['symbols'] or symbol in r['symbols']]
    return rules


@app.get('/api/rule-screen')
def rule_screen():
    return monitor.screen()


@app.post('/api/rule-screen')
def refresh_rule_screen():
    return monitor.screen(refresh=True)


@app.post('/api/rules')
def create_rule(body:RuleInput):
    validate_rule(body)
    if len(storage.rules())>=100: raise ValueError('本地版最多支持 100 条规则')
    with monitor.lock, storage.connect() as db:
        cur=db.execute('INSERT INTO rules(name,expression,symbols,enabled) VALUES(?,?,?,?)',
                       (body.name,body.expression,json.dumps(body.symbols),int(body.enabled)))
        ident=cur.lastrowid
    return {'id':ident}


@app.put('/api/rules/{ident}')
def update_rule(ident:int,body:RuleInput):
    validate_rule(body)
    with monitor.lock, storage.connect() as db:
        cur=db.execute('UPDATE rules SET name=?,expression=?,symbols=?,enabled=?,version=version+1 WHERE id=?',
                       (body.name,body.expression,json.dumps(body.symbols),int(body.enabled),ident))
        if not cur.rowcount: raise HTTPException(404,'规则不存在')
        db.execute('DELETE FROM rule_state WHERE rule_id=?',(ident,))
    return {'ok':True}


@app.delete('/api/rules/{ident}')
def delete_rule(ident:int):
    with monitor.lock, storage.connect() as db:
        db.execute('DELETE FROM rules WHERE id=?',(ident,))
    return {'ok':True}


@app.post('/api/rules/{ident}/toggle')
def toggle_rule(ident:int):
    with monitor.lock, storage.connect() as db:
        db.execute('UPDATE rules SET enabled=1-enabled WHERE id=?',(ident,))
    return {'ok':True}


class ScanInput(BaseModel):
    expression: str=Field(min_length=1,max_length=4000)
    symbols: list[str]=Field(default_factory=list,**LIST_LIMIT)


@app.post('/api/scan')
def scan(body:ScanInput):
    parse(body.expression)
    symbols=body.symbols or [x['symbol'] for x in storage.rows('SELECT symbol FROM watchlist')]
    results=[]
    for symbol in dict.fromkeys(symbols):
        item=instrument(symbol)
        try:
            market=get_market(item['symbol'])
            result=Evaluator(market).run(body.expression)
            if not monitor.current(market):
                result.update(matched=False,ready=False,reason='行情延迟，暂停判定')
            results.append({**item,**result,'source':market.source})
        except Exception as exc:
            results.append({**item,'matched':False,'ready':False,'error':str(exc)[:180]})
    return {'results':results,'scanned':len(results),'matched':sum(x['matched'] for x in results),'asof':str(now())}


@app.get('/api/alerts')
def alerts():
    result=storage.rows('''SELECT a.*,o.status AS delivery_status,o.error AS delivery_error FROM alerts a
        LEFT JOIN outbox o ON o.alert_id=a.id ORDER BY a.id DESC LIMIT 200''')
    for item in result: item['evidence']=json.loads(item['evidence'])
    return result


@app.post('/api/alerts/read')
def read_alerts():
    with storage.connect() as db: db.execute('UPDATE alerts SET read=1')
    return {'ok':True}


class SettingsInput(BaseModel):
    source: Literal['demo','tushare','public']
    interval: int=Field(ge=60,le=3600)


@app.put('/api/settings')
def put_settings(body:SettingsInput):
    if body.source=='tushare' and not os.getenv('TUSHARE_TOKEN'):
        raise ValueError('请先在 App 顶部“运行”配置 Tushare 密钥。当前数据源保持不变。' if os.getenv('MONITOR_RUNTIME') == 'android' else '请先在本地 .env 配置 TUSHARE_TOKEN 并重启服务。当前数据源保持不变。')
    with monitor.lock, storage.connect() as db:
        for key,val in (body.model_dump() if hasattr(body, 'model_dump') else body.dict()).items():
            db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(key,json.dumps(val)))
        monitor.cache.clear()
        monitor.errors.clear()
        monitor.screen_cache=None
    return {'ok':True}


@app.post('/api/refresh')
def refresh():
    completed=monitor.tick()
    return {'ok':completed,'last_sync':monitor.last_sync,'errors':dict(monitor.errors)}


class WorkspaceInput(BaseModel):
    format: Literal['guanlan-workspace-v1']
    watchlist: list[WatchInput] = Field(default_factory=list, **LIST_LIMIT)
    rules: list[RuleInput] = Field(default_factory=list, **({'max_length':100} if hasattr(BaseModel,'model_dump') else {'max_items':100}))


@app.get('/api/workspace/export')
def export_workspace():
    return {'format':'guanlan-workspace-v1',
            'watchlist':[{'symbol':x['symbol']} for x in storage.rows('SELECT symbol FROM watchlist ORDER BY symbol')],
            'rules':[{k:r[k] for k in ('name','expression','symbols','enabled')} for r in storage.rules()]}


@app.post('/api/workspace/import')
def import_workspace(body:WorkspaceInput):
    # Validate every rule before a single write. Import merges, never removes local data.
    instruments = {instrument(x.symbol)['symbol']:instrument(x.symbol) for x in body.watchlist}
    for rule in body.rules:
        for symbol in rule.symbols:
            item = instrument(symbol)
            instruments[item['symbol']] = item
        validate_rule(rule, allowed_symbols=instruments.keys())
    with monitor.lock, storage.connect() as db:
        known = {r['symbol'] for r in db.execute('SELECT symbol FROM watchlist')}
        if len(known | instruments.keys()) > 200: raise ValueError('合并后自选不能超过 200 只')
        existing_rules = storage.rules()
        current = {(r['name'],r['expression'],tuple(sorted(r['symbols'])),r['enabled']) for r in existing_rules}
        rules = []
        for rule in body.rules:
            key = (rule.name,rule.expression,tuple(sorted(rule.symbols)),rule.enabled)
            if key not in current:
                current.add(key); rules.append(rule)
        if len(existing_rules) + len(rules) > 100: raise ValueError('合并后规则不能超过 100 条')
        for item in instruments.values():
            db.execute('INSERT OR IGNORE INTO watchlist(symbol,name,kind) VALUES(?,?,?)',(item['symbol'],item['name'],item['kind']))
        for rule in rules:
            db.execute('INSERT INTO rules(name,expression,symbols,enabled) VALUES(?,?,?,?)',(rule.name,rule.expression,json.dumps(rule.symbols),int(rule.enabled)))
        monitor.screen_cache = None
    return {'watchlist_added':len(instruments.keys()-known),'rules_added':len(rules)}


@app.get('/favicon.ico',include_in_schema=False)
def favicon():
    return RedirectResponse('/icon.svg')


if os.getenv('MONITOR_RUNTIME') != 'android':
    app.mount('/',StaticFiles(directory=str(ROOT/'web'),html=True),name='web')
