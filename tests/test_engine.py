import numpy as np
import pandas as pd
import pytest

from backend.indicators import CATALOG, calculate, series
from backend.market import DemoProvider, MarketData, TushareProvider
from backend.rules import Evaluator, align, parse


@pytest.mark.parametrize('name',[n for n,s in CATALOG.items() if s['available']])
def test_catalog_functions_are_callable(name,market):
    result=calculate(market.daily,name)
    assert len(result)==len(market.daily)
    assert list(result.columns)==CATALOG[name]['outputs']
    assert not np.isinf(result.to_numpy()).any()


def test_bollinger_formula_and_sma(market):
    close=market.daily['close']
    output=calculate(market.daily,'BOLL',kwargs={'timeperiod':20})
    assert output['middleband'].iloc[-1]==pytest.approx(close.tail(20).mean())
    assert output['upperband'].iloc[-1]==pytest.approx(close.tail(20).mean()+2*close.tail(20).std(ddof=0))
    assert series(market.daily,'MA',(5,)).iloc[-1]==pytest.approx(close.tail(5).mean())


def test_macd_definition(market):
    macd=calculate(market.daily,'MACD')
    np.testing.assert_allclose(macd.macdhist,macd.macd-macd.macdsignal,equal_nan=True)


def test_no_unfinished_bars_or_lunch_bars(market):
    assert market.bars('15m').index[-1]==pd.Timestamp('2026-11-06 14:30')
    assert market.bars('60m').index[-1]==pd.Timestamp('2026-11-06 14:00')
    assert market.daily.index[-1]==pd.Timestamp('2026-11-05 15:00')
    assert market.bars('1w').index[-1]==pd.Timestamp('2026-10-30 15:00')
    assert market.bars('1M').index[-1]==pd.Timestamp('2026-10-30 15:00')
    day=market.bars('60m').loc['2026-11-05']
    assert [t.strftime('%H:%M') for t in day.index]==['10:30','11:30','14:00','15:00']


def test_minute_and_daily_consistency_and_aggregation(market):
    minute=market.minute.loc['2026-11-05']
    day=market.daily.loc['2026-11-05'].iloc[0]
    assert minute['high'].max()==day['high']
    assert minute['low'].min()==day['low']
    assert minute['close'].iloc[-1]==day['close']
    assert minute['volume'].sum()==day['volume']
    bar=market.bars('15m').loc['2026-11-05 10:00']
    source=minute.loc['2026-11-05 09:46':'2026-11-05 10:00']
    assert bar['open']==source['open'].iloc[0]
    assert bar['volume']==source['volume'].sum()


def test_missing_minute_makes_interval_unknown(market):
    data=MarketData(market.minute.drop(pd.Timestamp('2026-11-06 14:29')),market.daily,'demo',market.asof)
    assert data.bars('15m').loc['2026-11-06 14:30'].isna().all()
    result=Evaluator(data).run('not (CLOSE(tf="15m") > 0)')
    assert not result['ready'] and not result['matched']


def test_ref_uses_native_period_before_alignment(market):
    result=Evaluator(market).run('REF(CLOSE(tf="1d"), 1) > 0 and RSI(14, tf="5m") >= 0')
    assert result['ready']
    ev=Evaluator(market)
    value=ev.visit(parse('REF(CLOSE(tf="1d"), 1) > 0').body.left)
    assert value.iloc[-1]==market.daily['close'].iloc[-2]


def test_alignment_preserves_unknown_and_has_no_backward_fill():
    a=pd.Series([1.,np.nan,3.],index=pd.date_range('2026-01-01',periods=3))
    b=pd.Series([10.],index=pd.to_datetime(['2026-01-02 12:00']))
    x,y=align(a,b)
    assert pd.isna(x.loc['2026-01-02 12:00'])
    assert pd.isna(y.iloc[0])
    assert y.iloc[-1]==10


def test_cross_and_rolling_conditions(market):
    result=Evaluator(market).run('EVERY(CLOSE() > 0, 3) and COUNT(RSI(14) >= 0, 5) == 5')
    assert result['matched']
    assert not Evaluator(market).run('CROSSUP(MA(5), MA(5))')['matched']
    data=MarketData(market.minute,market.daily.tail(3),'demo',market.asof)
    unknown=Evaluator(data).run('not (RSI(14) > 50)')
    assert not unknown['ready'] and not unknown['matched']
    unknown_or_true=Evaluator(data).run('RSI(14) > 50 or CLOSE() > 0')
    assert unknown_or_true['ready'] and unknown_or_true['matched']
    assert Evaluator(market).run('CLOSE() > 0\nand RSI(14) >= 0')['matched']


@pytest.mark.parametrize('expression',[
    '__import__("os").system("id")','CLOSE().__class__','[x for x in (1,2)]',
    '(lambda: 1)()', 'CLOSE()[0]', 'open("file")', 'CLOSE() ** 1000',
    'RSI(14, tf="1s") > 30','RSI(-3) > 0','REF(CLOSE(), -1) > 0',
    'RSI(14)', 'CLOSE() / 0 > 0', 'RSI(14, timeperiod=20) > 0',
    'RSI(14, tf="1d", tf="5m") > 0','VWAP(tf="1d") > 0'])
def test_expression_validation(expression,market):
    with pytest.raises((ValueError,TypeError)):
        Evaluator(market).run(expression)


def test_demo_is_deterministic_and_has_no_future(market):
    again=DemoProvider().fetch('510300.SH',market.asof)
    pd.testing.assert_frame_equal(again.minute,market.minute)
    assert all(market.minute.index<=market.asof)


def test_provider_units_and_auction_fold(monkeypatch):
    monkeypatch.setenv('TUSHARE_TOKEN','test-only')
    provider=TushareProvider()
    raw=pd.DataFrame([['20261105',1,3,1,2,5,6]],columns=['trade_date','open','high','low','close','vol','amount'])
    day=provider.normalize(raw,daily=True)
    assert day.volume.iloc[0]==500
    assert day.amount.iloc[0]==6000
    raw=pd.DataFrame([['2026-11-05 09:30',1,3,1,2,5,6],['2026-11-05 09:31',2,4,2,3,10,20]],columns=['time','open','high','low','close','vol','amount'])
    result=provider.normalize(raw)
    assert len(result)==1 and result.index[0]==pd.Timestamp('2026-11-05 09:31')
    assert result.volume.iloc[0]==15 and result.high.iloc[0]==4 and result.open.iloc[0]==1
