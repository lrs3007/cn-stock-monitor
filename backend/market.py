"""Source adapters and session-aware, closed-bar aggregation.

Synthetic data never silently replaces a failed live source.
All timestamps are Asia/Shanghai, stored without offsets internally.
"""
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from io import StringIO
from zoneinfo import ZoneInfo

import httpx
import numpy as np
import pandas as pd

from . import storage

TZ = ZoneInfo('Asia/Shanghai')
TIMEFRAMES = ['1m', '3m', '5m', '10m', '15m', '30m', '60m', '120m', '1d', '1w', '1M']
FIELDS = ['open', 'high', 'low', 'close', 'volume', 'amount']
INSTRUMENTS = [
    ('510300.SH', '沪深300ETF', 'ETF', 4.1), ('159915.SZ', '创业板ETF', 'ETF', 2.4),
    ('588000.SH', '科创50ETF', 'ETF', 1.2), ('510500.SH', '中证500ETF', 'ETF', 6.2),
    ('512100.SH', '中证1000ETF', 'ETF', 2.6), ('518880.SH', '黄金ETF', 'ETF', 6.0),
    ('513100.SH', '纳指ETF', 'ETF', 1.8), ('159941.SZ', '纳指ETF', 'ETF', 1.5),
    ('512880.SH', '证券ETF', 'ETF', 1.1), ('512760.SH', '芯片ETF', 'ETF', 1.2),
    ('600519.SH', '贵州茅台', '股票', 1500), ('300750.SZ', '宁德时代', '股票', 280),
    ('601318.SH', '中国平安', '股票', 55), ('600036.SH', '招商银行', '股票', 38),
    ('000001.SZ', '平安银行', '股票', 12), ('000333.SZ', '美的集团', '股票', 70),
    ('002594.SZ', '比亚迪', '股票', 100), ('601899.SH', '紫金矿业', '股票', 20),
    ('920002.BJ', '万达轴承', '股票', 70)]


def now():
    return pd.Timestamp(datetime.now(TZ).replace(tzinfo=None)).floor('min')


def instrument(code):
    code = code.upper().strip()
    if re.fullmatch(r'\d{6}', code):
        code += '.SH' if code[0] in '56' else '.BJ' if code[0] in '489' else '.SZ'
    if not re.fullmatch(r'\d{6}\.(SH|SZ|BJ)', code):
        raise ValueError('请输入六位证券代码，如 510300 或 600519.SH')
    found = next((x for x in INSTRUMENTS if x[0] == code), None)
    if found:
        return dict(zip(['symbol', 'name', 'kind', 'base'], found))
    kind = 'ETF' if code.startswith(('51', '52', '56', '58', '15', '16')) else '股票'
    return {'symbol': code, 'name': code[:6], 'kind': kind, 'base': 3 if kind == 'ETF' else 30}


@dataclass
class MarketData:
    minute: pd.DataFrame
    daily: pd.DataFrame
    source: str
    asof: pd.Timestamp
    calendar: object = None
    native: dict = field(default_factory=dict)
    issues: list = field(default_factory=list)
    calendar_until: object = None
    providers: dict = field(default_factory=dict)

    def bars(self, tf):
        if tf not in TIMEFRAMES:
            raise ValueError('不支持的周期：' + tf)
        if tf in self.native:
            return self.native[tf]
        if tf.endswith('m'):
            n = int(tf[:-1])
            base = max([1] + [int(k[:-1]) for k in self.native if k.endswith('m') and n % int(k[:-1]) == 0])
            frame = self.native.get(f'{base}m', self.minute)
            if frame.empty: return frame
            if n == 1:
                return frame
            times = frame.index
            minutes = times.hour * 60 + times.minute
            starts = np.where(minutes <= 690, 570, 780)
            slot = np.ceil((minutes - starts) / n).astype(int)
            ends = times.normalize() + pd.to_timedelta(starts + slot * n, unit='m')
            grouped = aggregate(frame, ends)
            complete = frame.groupby(ends)['close'].count() == n // base
            grouped.loc[~complete, :] = np.nan
            # Never release a partial interval, including the current session.
            return grouped[grouped.index <= frame.index[-1]]
        if tf == '1d':
            return self.daily
        frame = self.daily
        if frame.empty: return frame
        periods = frame.index.to_period('W-FRI' if tf == '1w' else 'M')
        grouped = aggregate(frame, periods)
        # Periods are released only after their last scheduled trading session.
        end_dates = []
        for period in grouped.index:
            end = period.end_time.normalize()
            if self.calendar_until is not None and end > self.calendar_until:
                # Unknown future holiday schedules must not close a period early.
                end_dates.append(pd.NaT)
                continue
            if self.calendar is not None:
                valid = self.calendar[(self.calendar >= period.start_time.normalize()) & (self.calendar <= end)]
                end = valid[-1] if len(valid) else end
            else:
                while end.weekday() > 4:
                    end -= pd.Timedelta(days=1)
            end_dates.append(end + pd.Timedelta(hours=15))
        grouped.index = pd.DatetimeIndex(end_dates)
        return grouped[grouped.index <= self.asof]


def aggregate(frame, labels):
    groups = frame.groupby(labels)
    result = groups.agg({'open': 'first', 'high': 'max', 'low': 'min',
                         'close': 'last', 'volume': 'sum', 'amount': 'sum'})
    # Missing constituents are unknown, including amount and volume.
    return result.where(groups.count().eq(groups.size(), axis=0))


class DemoProvider:
    """Deterministic synthetic OHLCV. Uses weekdays, NOT an exchange holiday calendar."""
    def fetch(self, symbol, asof=None):
        asof = asof if asof is not None else now()
        info = instrument(symbol)
        seed = int(hashlib.sha256(symbol.encode()).hexdigest()[:8], 16)
        dates = pd.bdate_range(asof.normalize() - pd.DateOffset(years=12), asof.normalize())
        day = (dates - pd.Timestamp('2000-01-01')).days.to_numpy()[:, None]
        minute = np.arange(241)[None, :]
        phase = seed % 300 / 30
        # Continuous daily endpoints with smooth synthetic intraday swings.
        def baseline(d):
            return .16 * np.sin(d / 171 + phase) + .07 * np.sin(d / 37 + phase) + .035 * np.sin(d / 8 + phase)
        first = baseline(day - 1)
        last = baseline(day)
        curve = first + (last-first)*minute/240 + .007*np.sin(minute/240*np.pi)*np.sin(minute/11+day+phase)
        prices = info['base'] * np.exp(curve)
        opens, closes = prices[:, :-1], prices[:, 1:]
        spread = .0005 * (1 + np.sin(day + minute[:, 1:] * 7 + phase)**2)
        highs = np.maximum(opens, closes)*(1+spread)
        lows = np.minimum(opens, closes)*(1-spread)
        volumes = (30000 * (1.5+np.sin(day*3+minute[:, 1:]/4+phase)) * (1.2+np.cos(minute[:, 1:]/240*2*np.pi)**2)).astype(float)
        if info['kind'] == 'ETF':
            volumes *= 12
        amounts = volumes * (opens+closes)/2
        daily = pd.DataFrame(dict(open=opens[:, 0], high=highs.max(axis=1), low=lows.min(axis=1),
                                  close=closes[:, -1], volume=volumes.sum(axis=1), amount=amounts.sum(axis=1)),
                             index=dates+pd.Timedelta(hours=15))
        daily = daily[daily.index <= asof]
        # 90 sessions provide 180 completed 120-minute bars.
        times = np.r_[np.arange(571, 691), np.arange(781, 901)]
        index = pd.DatetimeIndex((dates[-90:].values[:, None] + times[None, :].astype('timedelta64[m]')).ravel())
        frame = pd.DataFrame({key: array[-90:].ravel() for key, array in zip(FIELDS, [opens, highs, lows, closes, volumes, amounts])}, index=index)
        frame = frame[frame.index <= asof]
        return MarketData(frame, daily, 'demo', asof)


class TushareProvider:
    def __init__(self):
        self.token = os.getenv('TUSHARE_TOKEN', '')
        if not self.token:
            raise ValueError('未配置 TUSHARE_TOKEN。请在本地 .env 中设置并重启服务。')

    def request(self, api, **params):
        try:
            response = httpx.post('https://api.tushare.pro', json={'api_name': api, 'token': self.token, 'params': params}, timeout=25)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            raise ValueError('行情服务连接失败，请检查网络和接口状态') from None
        if payload.get('code') != 0:
            # Provider errors may echo request details: do not expose credentials.
            message = str(payload.get('msg', '权限或接口错误')).replace(self.token, '[redacted]')
            raise ValueError(f'{api}: {message[:180]}')
        data = payload.get('data') or {}
        return pd.DataFrame(data.get('items', []), columns=data.get('fields', []))

    def normalize(self, frame, daily=False, stock=True):
        if frame.empty:
            return pd.DataFrame(columns=FIELDS, index=pd.DatetimeIndex([]))
        col = 'trade_date' if daily else 'trade_time' if 'trade_time' in frame else 'time'
        index = pd.DatetimeIndex(pd.to_datetime(frame[col]))
        if daily:
            index += pd.Timedelta(hours=15)
        frame = frame.rename(columns={'vol': 'volume'}).copy()
        frame.index = index
        # Tushare daily units: volume in lots and amount in CNY thousands;
        # minute endpoints use shares/units and CNY. Normalize before aggregation.
        if daily:
            frame['volume'] = pd.to_numeric(frame['volume']) * 100
            frame['amount'] = pd.to_numeric(frame['amount']) * 1000
        frame = frame[FIELDS].astype(float).sort_index()
        frame = frame[~frame.index.duplicated(keep='last')]
        valid = (np.isfinite(frame).all(axis=1) & (frame['close'] > 0)
                 & (frame['open'] > 0) & (frame['low'] > 0)
                 & (frame['high'] >= frame[['open','close','low']].max(axis=1))
                 & (frame['low'] <= frame[['open','close']].min(axis=1))
                 & (frame['volume'] >= 0) & (frame['amount'] >= 0))
        frame.loc[~valid, :] = np.nan
        if not daily:
            m = frame.index.hour*60+frame.index.minute
            # 09:30/13:00 auction/boundary rows are not standalone minute bars.
            # Fold into the following minute to preserve volume and extremes.
            boundary = np.isin(m, [570, 780])
            frame.index = frame.index + pd.to_timedelta(boundary.astype(int), unit='m')
            frame = aggregate(frame, frame.index)
            m = frame.index.hour*60+frame.index.minute
            frame = frame[((m>570)&(m<=690))|((m>780)&(m<=900))]
        return frame[~frame.index.duplicated(keep='last')]

    def fetch(self, symbol, asof=None):
        asof = asof if asof is not None else now()
        etf = instrument(symbol)['kind'] == 'ETF'
        cached = storage.rows('SELECT * FROM market_cache WHERE symbol=? AND source=?', (symbol, 'tushare'))
        daily = minute = None
        cache = json.loads(cached[0]['payload']) if cached else {}
        if cache:
            daily = pd.read_json(StringIO(cache['daily']), orient='split')
            minute = pd.read_json(StringIO(cache['minute']), orient='split')
        if daily is None or cache.get('date') != str(asof.date()):
            daily = self.normalize(self.request('fund_daily' if etf else 'daily', ts_code=symbol,
                                                start_date=(asof-pd.DateOffset(years=12)).strftime('%Y%m%d'), end_date=asof.strftime('%Y%m%d')), daily=True)
        if minute is None or minute.empty:
            parts = []
            for start in pd.date_range(asof.normalize()-pd.Timedelta(days=60), asof.normalize(), freq='5D'):
                end = min(start+pd.Timedelta(days=5)-pd.Timedelta(seconds=1), asof)
                parts.append(self.normalize(self.request('etf_mins' if etf else 'stk_mins', ts_code=symbol, freq='1min',
                                                         start_date=str(start), end_date=str(end))))
            minute = pd.concat(parts)
        elif minute.index[-1].date() < (asof-pd.Timedelta(days=1)).date():
            # Repair interruptions; pagination keeps each request below row caps.
            for start in pd.date_range(minute.index[-1].normalize(), asof.normalize(), freq='5D'):
                end = min(start+pd.Timedelta(days=5)-pd.Timedelta(seconds=1), asof)
                part = self.normalize(self.request('etf_mins' if etf else 'stk_mins', ts_code=symbol, freq='1min', start_date=str(start), end_date=str(end)))
                minute = pd.concat([minute, part])
        latest = self.normalize(self.request('rt_etf_min_daily' if etf else 'rt_min_daily', ts_code=symbol, freq='1MIN'))
        minute = pd.concat([minute, latest]).sort_index()
        minute = minute[~minute.index.duplicated(keep='last')]
        minute = minute[(minute.index<=asof)&(minute.index>=asof-pd.Timedelta(days=140))]
        # Preserve internal holes as unknown rather than compressing time. No
        # synthetic prices are generated for missing observations.
        expected = []
        for day, observed in minute.groupby(minute.index.normalize()):
            offsets = np.r_[np.arange(571, 691), np.arange(781, 901)]
            grid = day + pd.to_timedelta(offsets, unit='m')
            expected.extend(grid[grid <= observed.index[-1]])
        minute = minute.reindex(pd.DatetimeIndex(expected))
        # A daily endpoint fetched before the close may remain yesterday's data.
        # Close today's bar from complete minute inputs without waiting a day.
        if len(minute):
            dates = minute.index.normalize()
            completed = aggregate(minute, dates)
            counts = minute.groupby(dates)['close'].count()
            completed = completed[counts == 240]
            completed.index = completed.index + pd.Timedelta(hours=15)
            completed = completed[completed.index <= asof]
            daily = pd.concat([daily, completed]).sort_index()
            daily = daily[~daily.index.duplicated(keep='last')]
        daily = daily[daily.index<=asof]
        calendar_raw = self.request('trade_cal', exchange='SSE', start_date=(asof-pd.Timedelta(days=400)).strftime('%Y%m%d'), end_date=(asof+pd.Timedelta(days=40)).strftime('%Y%m%d'))
        calendar = pd.DatetimeIndex(pd.to_datetime(calendar_raw.loc[calendar_raw['is_open'].astype(int)==1, 'cal_date']))
        if minute.empty or daily.empty:
            raise ValueError('行情返回为空，请检查证券代码与股票/ETF分钟权限')
        with storage.connect() as db:
            db.execute('INSERT OR REPLACE INTO market_cache VALUES(?,?,?,?)', (symbol, 'tushare', json.dumps({'date': str(asof.date()), 'minute': minute.to_json(orient='split'), 'daily': daily.to_json(orient='split')}), str(asof)))
        return MarketData(minute, daily, 'tushare', asof, calendar)
