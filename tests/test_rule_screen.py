from dataclasses import replace
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend import storage
from backend.main import app
from backend.service import Monitor
from backend.trading import trading_session
import backend.service as service_module


@pytest.mark.parametrize('clock,phase,active', [
    ('2026-11-06 09:15','preopen',False),
    ('2026-11-06 09:30','trading',True),
    ('2026-11-06 11:30','trading',True),
    ('2026-11-06 11:31','lunch',False),
    ('2026-11-06 12:59','lunch',False),
    ('2026-11-06 13:00','trading',True),
    ('2026-11-06 14:59','trading',True),
    ('2026-11-06 15:00','trading',True),
    ('2026-11-06 15:01','closed',False),
    ('2026-11-07 10:00','holiday',False),
    ('2026-10-01 10:00','holiday',False),
    ('2027-01-04 10:00','unknown',False),
])
def test_exchange_session_boundaries(clock,phase,active):
    calendar=pd.bdate_range('2026-09-25','2026-12-31')
    calendar=calendar[(calendar<'2026-10-01')|(calendar>'2026-10-07')]
    session=trading_session(pd.Timestamp(clock),'public',calendar)
    assert session['phase']==phase and session['active']==active
    if phase=='lunch': assert session['next_open']=='2026-11-06 13:00:00'
    if phase=='holiday' and '11-07' in clock: assert session['next_open']=='2026-11-09 09:30:00'


@pytest.fixture
def live_service(store,market,monkeypatch):
    calendar=pd.bdate_range('2014-01-01','2026-12-31')
    live=replace(market,source='public',calendar=calendar,calendar_until=calendar[-1])
    monkeypatch.setattr('backend.service.now',lambda:market.asof)
    service=Monitor()
    monkeypatch.setattr(service,'market',lambda symbol:live)
    monkeypatch.setattr(service,'session',lambda m=None:trading_session(service_module.now(),'public',calendar))
    with store.connect() as db:
        db.execute('DELETE FROM rules')
        db.execute('UPDATE settings SET value=? WHERE key=?',(json.dumps('public'),'source'))
    return service,live


def add_rule(name,symbols,expression='CLOSE() > 0',enabled=True):
    with storage.connect() as db:
        return db.execute('INSERT INTO rules(name,expression,symbols,enabled) VALUES(?,?,?,?)',
                          (name,expression,json.dumps(symbols),int(enabled))).lastrowid


def test_screen_isolates_scopes_and_uses_all_enabled_rules(store,live_service):
    service,_=live_service
    own=add_rule('ETF 正价格',['510300.SH'])
    stock=add_rule('股票低阈值',['600519.SH'],'CLOSE() < 0')
    disabled=add_rule('停用规则',[],enabled=False)
    shared=add_rule('共享规则',['510300.SH','159915.SZ'])
    unknown=add_rule('历史不足',['588000.SH'],'RSI(1000, tf="120m") > 0')
    result=service.screen()
    rows={r['symbol']:r for r in result['results']}
    assert result['matched']==2 and result['unknown']==1 and result['no_rules']==2
    assert {r['id'] for r in rows['510300.SH']['rules']}=={own,shared}
    assert [r['id'] for r in rows['159915.SZ']['rules']]==[shared]
    assert rows['600519.SH']['status']=='unmatched'
    assert rows['588000.SH']['status']=='unknown'
    assert not any(r['id']==disabled for row in result['results'] for r in row['rules'])
    assert not store.rows('SELECT * FROM alerts') and not store.rows('SELECT * FROM rule_state')
    # The background worker uses exactly the same outcomes and scope.
    service.tick()
    alarms=store.rows('SELECT rule_id,symbol FROM alerts')
    assert {(r['rule_id'],r['symbol']) for r in alarms}=={(own,'510300.SH'),(shared,'510300.SH'),(shared,'159915.SZ')}
    service.tick()
    assert len(store.rows('SELECT * FROM alerts'))==3
    assert service.screen()['matched']==2  # sustained hits remain visible


def test_new_rule_toggle_scope_edit_and_remove_invalidate_screen(store,live_service):
    service,_=live_service
    ident=add_rule('专属',['510300.SH'])
    assert service.screen()['matched']==1
    with store.connect() as db:
        db.execute('UPDATE rules SET symbols=?,version=version+1 WHERE id=?',(json.dumps(['600519.SH']),ident))
    result=service.screen()
    assert [r['symbol'] for r in result['results'] if r['matched']]==['600519.SH']
    with store.connect() as db: db.execute('UPDATE rules SET enabled=0 WHERE id=?',(ident,))
    assert service.screen()['matched']==0
    ident2=add_rule('通用',[])
    assert service.screen()['matched']==6
    with store.connect() as db: db.execute('DELETE FROM rules WHERE id=?',(ident2,))
    assert service.screen()['no_rules']==6


@pytest.mark.parametrize('clock',['2026-11-06 12:00','2026-11-06 16:00','2026-11-07 10:00'])
def test_off_hours_screen_is_reference_and_never_changes_alarm_state(store,live_service,monkeypatch,clock):
    service,_=live_service
    add_rule('专属',['510300.SH'])
    monkeypatch.setattr('backend.service.now',lambda:pd.Timestamp(clock))
    monkeypatch.setattr(service,'current',lambda data:True)  # isolate session policy from stale-data policy
    assert service.screen()['reference_only']
    service.tick()
    assert not store.rows('SELECT * FROM alerts')
    assert not store.rows('SELECT * FROM rule_state')


def test_stale_quote_cannot_appear_as_matching_rule(store,live_service,monkeypatch):
    service,_=live_service
    add_rule('专属',['510300.SH'])
    monkeypatch.setattr('backend.service.now',lambda:pd.Timestamp('2026-11-06 14:45'))
    result=service.screen()
    row=next(r for r in result['results'] if r['symbol']=='510300.SH')
    assert row['status']=='unknown' and not row['matched']
    service.tick()
    assert not store.rows('SELECT * FROM alerts')


def test_api_personal_rules_roundtrip_and_screen_without_notifications(store,market,monkeypatch):
    import backend.main as main
    service=Monitor()
    monkeypatch.setattr(main,'monitor',service)
    monkeypatch.setattr(service,'market',lambda symbol:market)
    with store.connect() as db: db.execute('DELETE FROM rules')
    with TestClient(app) as client:
        body={'name':'ETF 独立规则','expression':'RSI(14, tf="15m") > 0',
              'symbols':['510300','159915.SZ','510300.SH'],'enabled':True}
        response=client.post('/api/rules',json=body)
        assert response.status_code==200,response.text
        ident=response.json()['id']
        own=client.get('/api/rules',params={'symbol':'510300'}).json()
        assert own[0]['symbols']==['510300.SH','159915.SZ']
        assert client.get('/api/rules',params={'symbol':'600519'}).json()==[]
        screen=client.post('/api/rule-screen').json()
        assert screen['matched']==2 and screen['source']=='demo'
        assert client.get('/api/alerts').json()==[]
        assert client.put(f'/api/rules/{ident}',json={**body,'symbols':['600519.SH'],'enabled':False}).status_code==200
        assert client.get('/api/rule-screen').json()['matched']==0
        client.post(f'/api/rules/{ident}/toggle')
        updated=client.get('/api/rule-screen').json()
        assert [r['symbol'] for r in updated['results'] if r['matched']]==['600519.SH']
        assert client.post('/api/rules',json={**body,'symbols':['999999.SH']}).status_code==400
        assert client.delete(f'/api/rules/{ident}').status_code==200
        assert client.get('/api/rule-screen').json()['no_rules']==6


def test_worker_retains_history_collection_without_enabled_rules(store,live_service,monkeypatch):
    service,live=live_service
    fetched=[]
    def fetch(symbol):
        fetched.append(symbol)
        return live
    monkeypatch.setattr(service,'market',fetch)
    service.tick()
    assert len(fetched)==6
    assert service.screen()['no_rules']==6
    assert not store.rows('SELECT * FROM alerts')
