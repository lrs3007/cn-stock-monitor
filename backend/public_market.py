"""No-token Eastmoney/Sina OHLCV, shared by desktop and Android.

Requests have explicit timeouts. Persisted bars retain their upstream timestamps;
network failure never becomes synthetic data or a successful live update.
"""
import json
import re
import time
from io import StringIO

import httpx
import numpy as np
import pandas as pd

from . import storage
from .market import FIELDS, MarketData, instrument, now

SOURCE = 'public'
PERIODS = {'1m': 1, '5m': 5, '15m': 15, '30m': 30, '60m': 60, '1d': 101}
PRICE_VOLUME = ['open', 'high', 'low', 'close', 'volume']


def empty_frame():
    return pd.DataFrame(columns=FIELDS, index=pd.DatetimeIndex([]), dtype=float)


def expected_end(clock, calendar, tf='1m'):
    """Most recent exchange close for a period, including lunch and holidays."""
    sessions = calendar[calendar <= clock.normalize()]
    if not len(sessions): return None
    day = sessions[-1]
    minute = clock.hour * 60 + clock.minute
    if day < clock.normalize(): return day + pd.Timedelta(hours=15)
    if tf == '1d' or minute < 571:
        if minute >= 900: return day + pd.Timedelta(hours=15)
        return sessions[-2] + pd.Timedelta(hours=15) if len(sessions) > 1 else None
    n = int(tf[:-1])
    if minute >= 900: end = 900
    elif minute >= 780: end = 780 + (minute - 780) // n * n
    else: end = 570 + (min(minute, 690) - 570) // n * n
    if end == 780: end = 690
    if end == 570:
        return sessions[-2] + pd.Timedelta(hours=15) if len(sessions) > 1 else None
    return day + pd.Timedelta(minutes=end)


class PublicProvider:
    _retry_after = {}

    def request(self, url, **params):
        host = httpx.URL(url).host
        if time.monotonic() < self._retry_after.get(host, 0):
            raise ValueError('公开接口暂不可用，稍后自动重试')
        try:
            response = httpx.get(url, params=params, timeout=httpx.Timeout(12, connect=5),
                                 headers={'User-Agent': 'Mozilla/5.0', 'Referer':
                                          'https://finance.sina.com.cn/' if 'sina' in host else 'https://quote.eastmoney.com/'})
            response.raise_for_status()
            return response.text
        except (httpx.HTTPError, ImportError):
            # One unavailable host should not incur 6 timeouts per instrument.
            self._retry_after[host] = time.monotonic() + 30
            raise ValueError('公开行情连接失败，请检查网络或稍后重试') from None

    def calendar(self, asof):
        rows = storage.rows('SELECT payload FROM market_cache WHERE symbol=? AND source=?', ('__calendar__', SOURCE))
        cache = json.loads(rows[0]['payload']) if rows else {}
        if cache.get('date') == str(asof.date()):
            return pd.DatetimeIndex(cache['days']), []
        try:
            from .sina_calendar import decode_calendar
            raw = self.request('https://finance.sina.com.cn/realstock/company/klc_td_sh.txt')
            encoded = raw.split('=', 1)[1].split(';', 1)[0].strip().strip('"')
            calendar = pd.DatetimeIndex(decode_calendar(encoded)).normalize().unique().sort_values()
            if len(calendar) < 200 or calendar[-1] < asof.normalize():
                raise ValueError('交易日历未覆盖当前日期，已暂停信号判断')
            payload = {'date': str(asof.date()), 'days': calendar.astype(str).tolist()}
            with storage.connect() as db:
                db.execute('INSERT OR REPLACE INTO market_cache VALUES(?,?,?,?)', ('__calendar__', SOURCE, json.dumps(payload), str(asof)))
            return calendar, []
        except Exception:
            if cache:
                return pd.DatetimeIndex(cache['days']), ['交易日历更新失败，展示缓存并暂停信号判断']
            return pd.DatetimeIndex([]), ['交易日历不可用，已暂停信号判断']

    def download(self, symbol, tf, asof):
        failures = []
        for vendor in ('eastmoney', 'sina'):
            try:
                frame, name = getattr(self, 'download_' + vendor)(symbol, tf, asof)
                frame.attrs['provider'] = vendor
                return frame, name
            except ValueError as exc:
                failures.append(('东方财富' if vendor == 'eastmoney' else '新浪') + '：' + str(exc))
        raise ValueError('两个公开行情源均未取得数据（' + '；'.join(failures) + '）')

    @staticmethod
    def validate(frame, tf, asof, optional_amount=False):
        frame = frame.reindex(columns=FIELDS).apply(pd.to_numeric, errors='coerce')
        required = PRICE_VOLUME if optional_amount else FIELDS
        valid = (np.isfinite(frame[required]).all(axis=1) & (frame[['open','high','low','close']] > 0).all(axis=1)
                 & (frame['high'] >= frame[['open','low','close']].max(axis=1))
                 & (frame['low'] <= frame[['open','close']].min(axis=1))
                 & (frame['volume'] >= 0)
                 & (frame['amount'].isna() | (np.isfinite(frame['amount']) & (frame['amount'] >= 0))))
        frame.loc[~valid, :] = np.nan
        frame = frame.sort_index()
        frame = frame[~frame.index.duplicated(keep='last')]
        if tf != '1d':
            n = int(tf[:-1])
            m = frame.index.hour * 60 + frame.index.minute
            legal = (((m > 570) & (m <= 690) & ((m-570) % n == 0))
                     | ((m > 780) & (m <= 900) & ((m-780) % n == 0)))
            frame = frame[legal & (frame.index.second == 0)]
        frame = frame[frame.index <= asof]
        if frame.empty or frame['close'].notna().sum() == 0: raise ValueError('没有有效的已收盘 K 线')
        return frame

    def download_sina(self, symbol, tf, asof):
        code, exchange = symbol.split('.')
        raw = self.request('https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_data=/CN_MarketDataService.getKLineData',
                           symbol=exchange.lower()+code, scale=240 if tf == '1d' else PERIODS[tf], ma='no', datalen=1970)
        try:
            # Parse only a JSON array in the known wrapper; never execute remote JS.
            match = re.fullmatch(r'\s*(?:/\*.*?\*/\s*)?var\s+_data\s*=\s*\((\[.*\])\)\s*;?\s*', raw, re.S)
            if not match: raise ValueError()
            records = json.loads(match[1])
            if not isinstance(records, list) or not records: raise ValueError()
            frame = pd.DataFrame(records)
            frame.index = pd.DatetimeIndex(pd.to_datetime(frame.pop('day')))
            if tf == '1d': frame.index = frame.index.normalize() + pd.Timedelta(hours=15)
            # Sina returns shares / ETF units, not lots. Daily responses omit
            # turnover: leave it unknown, never approximate it as price * volume.
            return self.validate(frame, tf, asof, optional_amount=True), None
        except (ValueError, TypeError, KeyError):
            raise ValueError('行情为空或格式异常') from None

    def download_eastmoney(self, symbol, tf, asof):
        code, exchange = symbol.split('.')
        text = self.request('https://push2his.eastmoney.com/api/qt/stock/kline/get',
                            secid=f'{1 if exchange == "SH" else 0}.{code}', klt=PERIODS[tf], fqt=0,
                            beg=(asof-pd.DateOffset(years=12)).strftime('%Y%m%d') if tf == '1d' else '0',
                            end=asof.strftime('%Y%m%d'), lmt=4000 if tf == '1d' else 2000,
                            fields1='f1,f2,f3,f4,f5,f6', fields2='f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61')
        try:
            payload = json.loads(text)
            data = payload.get('data') or {}
            if payload.get('rc') != 0 or data.get('code') != code or not data.get('klines'):
                raise ValueError()
            records = [row.split(',')[:7] for row in data['klines']]
            frame = pd.DataFrame(records, columns=['time', 'open', 'close', 'high', 'low', 'volume', 'amount'])
            frame.index = pd.DatetimeIndex(pd.to_datetime(frame.pop('time')))
            if tf == '1d': frame.index += pd.Timedelta(hours=15)
            frame = frame[FIELDS].apply(pd.to_numeric, errors='coerce')
            # Eastmoney OHLCV endpoints return volume in lots, amount in CNY.
            frame['volume'] *= 100
            return self.validate(frame, tf, asof), data.get('name', code)
        except (ValueError, TypeError, KeyError):
            raise ValueError(f'{symbol} 的 {tf} 行情为空或格式异常，请检查证券代码和接口状态') from None

    def fetch(self, symbol, asof=None):
        asof = asof if asof is not None else now()
        info = instrument(symbol)
        if symbol.endswith('.BJ'):
            raise ValueError('免 Token 数据源当前支持沪深股票和 ETF；北交所尚未验证')
        rows = storage.rows('SELECT payload FROM market_cache WHERE symbol=? AND source=?', (symbol, SOURCE))
        cache = json.loads(rows[0]['payload']) if rows else {}
        calendar, issues = self.calendar(asof)
        frames, targets = {}, cache.get('targets', {})
        providers = cache.get('providers', {})
        name = cache.get('name', info['name'])
        for tf in PERIODS:
            old = pd.read_json(StringIO(cache['frames'][tf]), orient='split') if tf in cache.get('frames', {}) else empty_frame()
            target = expected_end(asof, calendar, tf) if len(calendar) else None
            # During a closed session a successfully fetched bar is reused.
            complete = target is not None and len(old) and old.index[-1] >= target and old.iloc[-1][PRICE_VOLUME].notna().all()
            # Validate old-version caches once to record vendor provenance and
            # replace incomplete historical series even during a closed session.
            if complete and providers.get(tf) and targets.get(tf) == str(target):
                frames[tf] = old
                continue
            try:
                fresh, fresh_name = self.download(symbol, tf, asof)
                name = fresh_name or name
                vendor = fresh.attrs.get('provider', 'eastmoney')
                # Start a consistent series when changing vendor. Legacy caches
                # were all Eastmoney; don't splice unknown vendor/volume units.
                if providers.get(tf, 'eastmoney') != vendor: old = empty_frame()
                merged = pd.concat([old, fresh]).sort_index()
                merged = merged[~merged.index.duplicated(keep='last')]
                frames[tf] = merged.tail(5000 if tf == '1d' else 40000)
                targets[tf] = str(target)
                providers[tf] = vendor
            except ValueError as exc:
                frames[tf] = old
                issues.append(f'{tf}：{exc}；保留历史缓存，暂停信号判断')
        if frames['1m'].empty and frames['1d'].empty:
            raise ValueError(issues[-1] if issues else '未取得真实行情')
        # Explicit holes on observed sessions prevent rolling windows from silently
        # treating missing minutes or trading days as adjacent observations.
        for tf, frame in frames.items():
            if frame.empty: continue
            end = expected_end(asof, calendar, tf) if len(calendar) else frame.index[-1]
            end = max(frame.index[-1], end) if end is not None else frame.index[-1]
            days = calendar[(calendar >= frame.index[0].normalize()) & (calendar <= end.normalize())]
            if not len(days): days = frame.index.normalize().unique()
            offsets = [900] if tf == '1d' else list(range(570+int(tf[:-1]),691,int(tf[:-1])))+list(range(780+int(tf[:-1]),901,int(tf[:-1])))
            grid = pd.DatetimeIndex((days.values[:,None] + np.array(offsets, dtype='timedelta64[m]')[None,:]).ravel())
            frames[tf] = frame.reindex(grid[(grid >= frame.index[0]) & (grid <= end)])
        payload = {'name': name, 'frames': {tf: f.to_json(orient='split', date_format='iso', double_precision=15) for tf,f in frames.items()}, 'targets': targets, 'providers': providers}
        with storage.connect() as db:
            db.execute('INSERT OR REPLACE INTO market_cache VALUES(?,?,?,?)', (symbol, SOURCE, json.dumps(payload), str(asof)))
            db.execute('UPDATE watchlist SET name=? WHERE symbol=?', (name, symbol))
        return MarketData(frames.pop('1m'), frames.pop('1d'), SOURCE, asof, calendar,
                          native=frames, issues=issues, calendar_until=calendar[-1] if len(calendar) else pd.Timestamp.min,
                          providers=providers)
