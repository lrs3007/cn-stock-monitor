"""Contract tests use local fixtures, never real network or credentials."""
import numpy as np
import pandas as pd

from backend.market import TushareProvider, MarketData
from backend.service import Monitor
from backend.rules import Evaluator


def test_adapter_refreshes_closed_day_and_retains_missing_minutes(store,monkeypatch):
    monkeypatch.setenv('TUSHARE_TOKEN','contract-placeholder')
    asof=pd.Timestamp('2026-11-06 15:02')
    offsets=np.r_[np.arange(571,691),np.arange(781,901)]
    times=asof.normalize()+pd.to_timedelta(offsets,unit='m')
    minutes=pd.DataFrame({'time':times.astype(str),'open':2.,'high':3.,'low':1.,'close':2.5,'vol':10.,'amount':25.})
    # Yesterday includes a missing internal minute. It must not be compressed away.
    yesterday=minutes.drop(index=4).copy()
    yesterday['time']=pd.to_datetime(yesterday['time'])-pd.Timedelta(days=1)
    daily=pd.DataFrame([['20261105',2,3,1,2.2,24,.06]],columns=['trade_date','open','high','low','close','vol','amount'])
    def request(self,api,**params):
        if api=='fund_daily': return daily.copy()
        if api=='etf_mins': return yesterday.rename(columns={'time':'trade_time'}).copy()
        if api=='rt_etf_min_daily': return minutes.copy()
        if api=='trade_cal': return pd.DataFrame({'cal_date':['20261105','20261106','20261109'],'is_open':[1,1,1]})
        raise AssertionError(api)
    monkeypatch.setattr(TushareProvider,'request',request)
    data=TushareProvider().fetch('510300.SH',asof)
    assert data.daily.index[-1]==pd.Timestamp('2026-11-06 15:00')
    assert data.daily.iloc[-1]['close']==2.5
    assert data.daily.iloc[-1]['volume']==2400
    assert data.minute.loc['2026-11-05 09:35'].isna().all()
    assert len(data.minute.loc['2026-11-05'])==240
    # A fresh instance reads persisted source-specific history and updates it.
    again=TushareProvider().fetch('510300.SH',asof)
    assert again.daily.iloc[-1]['close']==2.5
    assert store.rows('SELECT source FROM market_cache')[0]['source']=='tushare'


def test_stale_live_data_cannot_create_alerts(store,market,monkeypatch):
    clock=pd.Timestamp('2026-11-06 14:45')
    monkeypatch.setattr('backend.service.now',lambda:clock)
    live=MarketData(market.minute,market.daily,'tushare',clock,pd.bdate_range('2026-11-01','2026-11-10'))
    monitor=Monitor()
    assert not monitor.current(live)
    monitor.record(store.rules()[0],{'symbol':'510300.SH','name':'ETF'},live,Evaluator(live).run('CLOSE() > 0'))
    assert not store.rows('SELECT * FROM alerts')


def test_week_closes_before_holiday_friday(market):
    asof=pd.Timestamp('2026-11-05 15:01')
    calendar=pd.DatetimeIndex(pd.to_datetime(['2026-11-02','2026-11-03','2026-11-04','2026-11-05','2026-11-09']))
    data=MarketData(market.minute[market.minute.index<=asof],market.daily,'tushare',asof,calendar)
    assert data.bars('1w').index[-1]==pd.Timestamp('2026-11-05 15:00')


def test_mail_retry_queue_and_success(store,market,monkeypatch):
    for key,value in {'SMTP_HOST':'smtp.invalid','SMTP_FROM':'test@example.invalid','ALERT_EMAIL':'owner@example.invalid'}.items():
        monkeypatch.setenv(key,value)
    calls=[]
    class FakeSMTP:
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def send_message(self,message):
            calls.append(message)
            if len(calls)==1:raise OSError('fixture failure')
    monkeypatch.setattr('backend.service.smtplib.SMTP_SSL',FakeSMTP)
    service=Monitor()
    service.record(store.rules()[0],{'symbol':'510300.SH','name':'ETF'},market,Evaluator(market).run('CLOSE()>0'))
    service.deliver()
    row=store.rows('SELECT * FROM outbox')[0]
    assert row['status']=='pending' and row['attempts']==1 and row['retry_at']>0
    with store.connect() as db:db.execute('UPDATE outbox SET retry_at=0')
    service.deliver()
    assert store.rows('SELECT * FROM outbox')[0]['status']=='sent'
    assert str(calls[-1]['Subject']).startswith('[演示]')
