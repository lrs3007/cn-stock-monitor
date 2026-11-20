import json
import pytest
from fastapi.testclient import TestClient

from backend.main import app, monitor
from backend.rules import Evaluator
from backend.service import Monitor


def test_alarm_transitions_and_restart_deduplication(store,market):
    rule=store.rules()[0]
    item={'symbol':'510300.SH','name':'沪深300ETF'}
    result=Evaluator(market).run('CLOSE() > 0')
    service=Monitor()
    service.record(rule,item,market,result)
    service.record(rule,item,market,result)
    Monitor().record(rule,item,market,result)
    assert len(store.rows('SELECT * FROM alerts'))==1
    assert len(store.rows('SELECT * FROM outbox'))==1
    assert store.rows('SELECT * FROM outbox')[0]['status']=='disabled'
    result['matched']=False
    service.record(rule,item,market,result)
    result.update(matched=True,bar_time='2026-11-06 15:00:00')
    service.record(rule,item,market,result)
    assert len(store.rows('SELECT * FROM alerts'))==2
    result.update(ready=False,matched=True,bar_time='2026-11-09 15:00:00')
    service.record(rule,item,market,result)
    assert len(store.rows('SELECT * FROM alerts'))==2


def test_api_workflow_and_failed_live_switch(store,monkeypatch):
    monkeypatch.delenv('TUSHARE_TOKEN',raising=False)
    monitor.cache.clear()
    with TestClient(app) as client:
        assert client.get('/').status_code==200
        status=client.get('/api/status').json()
        assert status['source']=='demo' and status['indicator_count']>150
        watch=client.get('/api/watchlist').json()
        assert len(watch)==6 and all(x['price']>0 for x in watch)
        assert client.post('/api/watchlist',json={'symbol':'512880'}).status_code==200
        assert len(client.get('/api/watchlist').json())==7
        chart=client.get('/api/chart',params={'symbol':'510300.SH','tf':'15m','indicator':'RSI'}).json()
        assert len(chart['bars'])==100 and chart['closed_only']
        assert chart['bars'][-1]['indicator']['real']>=0
        rule={'name':'测试 · 正价格','expression':'CLOSE() > 0','symbols':['510300.SH'],'enabled':True}
        created=client.post('/api/rules',json=rule)
        assert created.status_code==200,created.text
        ident=created.json()['id']
        scan=client.post('/api/scan',json={'expression':rule['expression'],'symbols':rule['symbols']}).json()
        assert scan['matched']==1
        client.post('/api/refresh')
        alerts=client.get('/api/alerts').json()
        assert any(a['rule_id']==ident and a['source']=='demo' and a['evidence'] for a in alerts)
        count=len(alerts)
        client.post('/api/refresh')
        assert len(client.get('/api/alerts').json())==count
        assert client.post('/api/alerts/read').status_code==200
        assert client.get('/api/status').json()['unread']==0
        assert client.put('/api/settings',json={'source':'tushare','interval':60}).status_code==400
        assert client.get('/api/status').json()['source']=='demo'
        assert client.post('/api/rules',json={**rule,'expression':'__import__("os")'}).status_code==400
        assert client.post('/api/watchlist',json={'symbol':'../secret'}).status_code==400
        assert client.post('/api/alerts/read',headers={'Origin':'https://evil.test'}).status_code==403
        assert client.put(f'/api/rules/{ident}',json={**rule,'expression':'CLOSE() < 0'}).status_code==200
        assert not store.rows('SELECT * FROM rule_state WHERE rule_id=?',(ident,))
        assert client.delete(f'/api/rules/{ident}').status_code==200
        assert len(client.get('/api/alerts').json())==count
        assert client.delete('/api/watchlist/512880.SH').status_code==200


def test_live_provider_failure_never_falls_back_to_demo(store,monkeypatch):
    monkeypatch.setenv('TUSHARE_TOKEN','placeholder')
    with store.connect() as db: db.execute('UPDATE settings SET value=? WHERE key=?',(json.dumps('tushare'),'source'))
    def fail(*args,**kwargs): raise ValueError('模拟行情接口失效')
    monkeypatch.setattr('backend.market.TushareProvider.fetch',fail)
    service=Monitor()
    with pytest.raises(ValueError,match='接口失效'):service.market('510300.SH')
    service.tick()
    assert service.errors
    assert not store.rows('SELECT * FROM alerts')
