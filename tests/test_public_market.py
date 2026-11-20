import json

import numpy as np
import pandas as pd
import pytest

from backend import indicators
from backend.market import MarketData, aggregate
from backend.public_market import PublicProvider, PERIODS, expected_end
from backend.service import Monitor


@pytest.mark.parametrize('clock,tf,expected', [
    ('2026-11-06 09:34','5m','2026-11-05 15:00'),
    ('2026-11-06 09:35','5m','2026-11-06 09:35'),
    ('2026-11-06 12:15','1m','2026-11-06 11:30'),
    ('2026-11-06 13:04','5m','2026-11-06 11:30'),
    ('2026-11-06 14:59','1d','2026-11-05 15:00'),
    ('2026-11-07 10:00','60m','2026-11-06 15:00'),
])
def test_expected_closed_period(clock,tf,expected):
    calendar=pd.bdate_range('2026-11-02','2026-11-10')
    assert expected_end(pd.Timestamp(clock),calendar,tf)==pd.Timestamp(expected)


def test_public_normalizes_units_and_rejects_future_bar(monkeypatch):
    rows=['2026-11-06 09:35,2,2.2,2.3,1.9,10,2100,0,0,0,0',
          '2026-11-06 09:40,2.2,2.3,2.4,2.1,20,4500,0,0,0,0',
          '2026-11-06 09:45,0,2.3,2.4,2.1,20,4500,0,0,0,0']
    def request(self,url,**params):
        assert params['secid']=='1.510300' and params['fqt']==0 and params['klt']==5
        return json.dumps({'rc':0,'data':{'code':'510300','name':'ETF','klines':rows}})
    monkeypatch.setattr(PublicProvider,'request',request)
    provider=PublicProvider()
    frame,name=provider.download('510300.SH','5m',pd.Timestamp('2026-11-06 09:38'))
    assert len(frame)==1 and name=='ETF'
    assert frame.iloc[0]['volume']==1000 and frame.iloc[0]['amount']==2100
    frame,_=provider.download('510300.SH','5m',pd.Timestamp('2026-11-06 09:46'))
    assert frame.iloc[-1].isna().all()


def test_public_persists_native_history_and_pauses_on_failure(store,market,monkeypatch):
    clock=pd.Timestamp('2026-11-06 14:37')
    calendar=pd.bdate_range('2014-01-01','2026-12-31')
    calls=[]
    monkeypatch.setattr(PublicProvider,'calendar',lambda self,asof:(calendar,[]))
    def download(self,symbol,tf,asof):
        calls.append(tf)
        return market.bars(tf).copy(),'真实测试ETF'
    monkeypatch.setattr(PublicProvider,'download',download)
    monkeypatch.setattr('backend.service.now',lambda:clock)
    first=PublicProvider().fetch('510300.SH',clock)
    assert set(calls)==set(PERIODS)
    assert Monitor().current(first)
    assert first.source=='public'
    assert len(first.bars('120m'))>100
    calls.clear()
    second=PublicProvider().fetch('510300.SH',clock)
    assert not calls
    pd.testing.assert_frame_equal(second.minute,first.minute,check_exact=False,rtol=1e-9)
    assert store.rows('SELECT name FROM watchlist WHERE symbol="510300.SH"')[0]['name']=='真实测试ETF'
    def failed(*args,**kwargs): raise ValueError('接口故障')
    monkeypatch.setattr(PublicProvider,'download',failed)
    clock+=pd.Timedelta(minutes=1)
    failed_data=PublicProvider().fetch('510300.SH',clock)
    assert failed_data.issues and not Monitor().current(failed_data)
    assert failed_data.minute.iloc[-1].isna().all()
    assert failed_data.minute['close'].dropna().iloc[-1]==pytest.approx(first.minute.iloc[-1]['close'])


def test_missing_minute_is_unknown_and_recursive_indicator_recovers(market):
    frame=market.minute.tail(200).copy()
    frame.iloc[80]=np.nan
    rsi=indicators.calculate(frame,'RSI')['real']
    assert pd.isna(rsi.iloc[80]) and pd.isna(rsi.iloc[90])
    assert np.isfinite(rsi.iloc[-1])
    expected=indicators.calculate(frame.iloc[81:],'RSI').iloc[-1,0]
    assert rsi.iloc[-1]==pytest.approx(expected)
    vwap=indicators.calculate(frame,'VWAP')
    assert vwap.iloc[-1].isna().all()
    grouped=aggregate(frame,frame.index.normalize())
    assert grouped.iloc[-1].isna().all()


def test_native_periods_do_not_require_one_minute_history(market):
    native={tf:market.bars(tf) for tf in ['5m','15m','30m','60m']}
    data=MarketData(market.minute.tail(240),market.daily,'public',market.asof,native=native)
    assert data.bars('60m').equals(native['60m'])
    assert len(data.bars('120m'))>100
    assert indicators.calculate(data.bars('120m'),'MACD').iloc[-1].notna().all()


def test_uncovered_calendar_does_not_close_future_week(market):
    calendar=pd.bdate_range('2026-11-02','2026-11-04')
    data=MarketData(market.minute,market.daily,'public',pd.Timestamp('2026-11-06 16:00'),calendar,
                    calendar_until=calendar[-1])
    assert data.bars('1w').index[-1]<pd.Timestamp('2026-11-01')


def test_public_source_available_without_token(store,monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app,monitor
    monkeypatch.delenv('TUSHARE_TOKEN',raising=False)
    with TestClient(app) as client:
        assert client.put('/api/settings',json={'source':'public','interval':60}).status_code==200
        assert client.get('/api/status').json()['source']=='public'
    monitor.cache.clear()


@pytest.mark.parametrize('symbol', ['510300.SH', '159915.SZ', '600519.SH', '300750.SZ'])
def test_sina_fallback_keeps_stock_and_etf_units(monkeypatch, symbol):
    calls = []
    def request(self, url, **params):
        calls.append(url)
        if 'eastmoney' in url: raise ValueError('连接断开')
        code, exchange = symbol.split('.')
        assert params == {'symbol': exchange.lower()+code, 'scale':5, 'ma':'no', 'datalen':1970}
        rows = [{'day':day, 'open':'4', 'high':'4.2', 'low':'3.9', 'close':'4.1',
                 'volume':'1000', 'amount':'4100'} for day in ['2026-11-06 09:35:00', '2026-11-06 09:40:00']]
        return '/* upstream comment */\nvar _data=(' + json.dumps(rows) + ');'
    monkeypatch.setattr(PublicProvider, 'request', request)
    frame, name = PublicProvider().download(symbol, '5m', pd.Timestamp('2026-11-06 09:38'))
    assert len(calls) == 2 and len(frame) == 1
    assert frame.iloc[-1]['volume'] == 1000 and frame.iloc[-1]['amount'] == 4100
    assert frame.attrs['provider'] == 'sina' and name is None


def test_sina_daily_amount_is_unknown_and_current_day_is_not_closed(monkeypatch):
    def request(self, url, **params):
        assert params['scale'] == 240
        return 'var _data=(' + json.dumps([
            {'day':day, 'open':4, 'high':4.2, 'low':3.9, 'close':4.1, 'volume':1000}
            for day in ['2026-11-05', '2026-11-06']]) + ');'
    monkeypatch.setattr(PublicProvider, 'request', request)
    frame, _ = PublicProvider().download_sina('510300.SH','1d',pd.Timestamp('2026-11-06 14:38'))
    assert list(frame.index) == [pd.Timestamp('2026-11-05 15:00')]
    assert frame.iloc[0]['close'] == 4.1 and pd.isna(frame.iloc[0]['amount'])


@pytest.mark.parametrize('raw', ['null', 'var _data=([]);', 'var _data=([{}]);', 'var _data=([]);alert(1);'])
def test_sina_rejects_malformed_or_executable_response(monkeypatch, raw):
    monkeypatch.setattr(PublicProvider, 'request', lambda *args, **kwargs:raw)
    with pytest.raises(ValueError, match='格式异常'):
        PublicProvider().download_sina('510300.SH','1d',pd.Timestamp('2026-11-06 16:00'))


def test_missing_turnover_does_not_block_price_rules_but_amount_is_unknown(market, monkeypatch):
    from dataclasses import replace
    from backend.rules import Evaluator
    data = replace(market, source='public', daily=market.daily.assign(amount=np.nan),
                   calendar=pd.bdate_range('2014-01-01','2026-12-31'))
    monkeypatch.setattr('backend.service.now',lambda:data.asof)
    assert Monitor().current(data)
    assert Evaluator(data).run('RSI(14) > 0')['ready']
    result = Evaluator(data).run('AMOUNT() > 0')
    assert not result['ready'] and not result['matched']
    assert indicators.calculate(data.daily,'VWAP').isna().all().all()


def test_vendor_change_replaces_history_and_cache_keeps_optional_amount(store,market,monkeypatch):
    clock = market.asof
    calendar = pd.bdate_range('2014-01-01','2026-12-31')
    monkeypatch.setattr(PublicProvider, 'calendar', lambda self,asof:(calendar,[]))
    vendor = 'eastmoney'
    calls = []
    def download(self,symbol,tf,asof):
        calls.append(tf)
        frame = market.bars(tf).copy()
        if vendor == 'sina':
            frame = frame.tail(100)
            if tf == '1d': frame['amount'] = np.nan
        frame.attrs['provider'] = vendor
        return frame, '缓存名称' if vendor == 'eastmoney' else None
    monkeypatch.setattr(PublicProvider, 'download', download)
    PublicProvider().fetch('510300.SH',clock)
    # Old-version caches have no provenance, and must refresh even at the same close.
    rows = store.rows('SELECT payload FROM market_cache WHERE symbol=?',('510300.SH',))
    payload = json.loads(rows[0]['payload']); payload.pop('providers')
    with store.connect() as db:
        db.execute('UPDATE market_cache SET payload=? WHERE symbol=?',(json.dumps(payload),'510300.SH'))
    vendor = 'sina'
    second = PublicProvider().fetch('510300.SH',clock)
    assert len(second.daily) == 100 and second.daily['amount'].isna().all()
    assert set(second.providers.values()) == {'sina'}
    assert store.rows('SELECT name FROM watchlist WHERE symbol=?',('510300.SH',))[0]['name'] == '缓存名称'
    calls.clear()
    cached = PublicProvider().fetch('510300.SH',clock)
    assert not calls and cached.providers == second.providers


def test_host_backoff_does_not_block_other_vendor(monkeypatch):
    import httpx
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        if 'eastmoney' in url: raise httpx.ConnectError('offline')
        return httpx.Response(200, text='ok', request=httpx.Request('GET',url))
    monkeypatch.setattr(PublicProvider, '_retry_after', {})
    monkeypatch.setattr(httpx, 'get', get)
    provider = PublicProvider()
    for _ in range(2):
        with pytest.raises(ValueError): provider.request('https://push2his.eastmoney.com/api/test')
    assert provider.request('https://quotes.sina.cn/api/test') == 'ok'
    assert len(calls) == 2
