"""One indicator engine for charts, screening and alerts. TA-Lib + A-share formulas."""
import numpy as np
import pandas as pd
import os
if os.getenv('MONITOR_TALIB_LIBRARY'):
    from . import native_talib as talib
    from .native_talib import abstract
else:
    import talib
    from talib import abstract

CUSTOM = {
    'KDJ': ({'n': 9, 'm1': 3, 'm2': 3}, ['k', 'd', 'j'], '随机指标'),
    'BIAS': ({'n': 6}, ['bias'], '乖离率'),
    'BBI': ({'n1': 3, 'n2': 6, 'n3': 12, 'n4': 24}, ['bbi'], '多空指标'),
    'DMI': ({'n': 14}, ['pdi', 'mdi', 'adx', 'adxr'], '趋向指标'),
    'DMA': ({'fast': 10, 'slow': 50, 'm': 10}, ['ddd', 'ama'], '平行线差'),
    'PSY': ({'n': 12, 'm': 6}, ['psy', 'ma'], '心理线'),
    'VR': ({'n': 26}, ['vr'], '成交量变异率'),
    'BRAR': ({'n': 26}, ['br', 'ar'], '情绪指标'),
    'CR': ({'n': 26}, ['cr'], '能量指标'),
    'EMV': ({'n': 14, 'm': 9}, ['emv', 'ma'], '简易波动'),
    'DPO': ({'n': 20}, ['dpo'], '区间震荡'),
    'VWAP': ({}, ['vwap'], '日内成交均价'),
    'DONCHIAN': ({'n': 20}, ['upper', 'middle', 'lower'], '唐奇安通道'),
    'KELTNER': ({'n': 20, 'atr_n': 10, 'multiplier': 2}, ['upper', 'middle', 'lower'], '肯特纳通道'),
    'SUPERTREND': ({'n': 10, 'multiplier': 3}, ['trend', 'direction'], '超级趋势'),
    'ASI': ({'limit': 3}, ['asi'], '振动升降指标'),
}
ALIASES = {'MA': 'SMA', 'BOLL': 'BBANDS', 'WR': 'WILLR', 'WPR': 'WILLR', 'VOL': 'VOLUME'}
LINES = {'MACD': {'dif': 'macd', 'dea': 'macdsignal', 'hist': 'macdhist'},
         'BBANDS': {'upper': 'upperband', 'middle': 'middleband', 'lower': 'lowerband'}}
GROUPS = {'Overlap Studies': '趋势与通道', 'Momentum Indicators': '动量与震荡',
          'Volume Indicators': '量价指标', 'Volatility Indicators': '波动率',
          'Pattern Recognition': 'K线形态', 'Cycle Indicators': '周期指标',
          'Statistic Functions': '统计运算', 'Price Transform': '价格变换',
          'Math Transform': '数学运算', 'Math Operators': '数学运算'}


def catalog():
    result = []
    for group, names in talib.get_function_groups().items():
        for name in names:
            fn = abstract.Function(name)
            info = fn.info
            result.append({'name': name, 'label': info['display_name'], 'group': GROUPS.get(group, group),
                           'parameters': dict(fn.parameters), 'outputs': fn.output_names,
                           'available': name != 'MAVP',
                           'note': '需外部动态周期序列，当前版本未开放' if name == 'MAVP' else ''})
    for name, (params, outputs, label) in CUSTOM.items():
        result.append({'name': name, 'label': label, 'group': 'A股常用补充', 'parameters': params, 'outputs': outputs, 'available': True, 'note': ''})
    return result


CATALOG = {x['name']: x for x in catalog()}


def specification(name):
    name = ALIASES.get(name.upper(), name.upper())
    if name not in CATALOG or not CATALOG[name]['available']:
        raise ValueError(f'不支持的指标：{name}')
    return name, CATALOG[name]


def parameters(name, args, kwargs):
    name, spec = specification(name)
    defaults = spec['parameters'].copy()
    keys = list(defaults)
    if len(args) > len(keys):
        raise ValueError(f'{name} 最多接受 {len(keys)} 个参数')
    for key, value in zip(keys, args):
        defaults[key] = value
    for key, value in kwargs.items():
        if key not in defaults:
            raise ValueError(f'{name} 没有参数 {key}')
        if key in keys[:len(args)]:
            raise ValueError(f'{name} 的 {key} 被重复指定')
        defaults[key] = value
    for key, value in defaults.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not np.isfinite(value):
            raise ValueError(f'{key} 必须是有限数值')
        original = spec['parameters'][key]
        if isinstance(original, int):
            if int(value) != value:
                raise ValueError(f'{key} 必须是整数')
            defaults[key] = int(value)
        if value < 0 or value > 1000:
            raise ValueError(f'{key} 需要在 0–1000 之间')
        if (key.startswith('n') or key in ['m', 'm1', 'm2', 'fast', 'slow', 'atr_n', 'limit'] or 'period' in key) and value < 1:
            raise ValueError(f'{key} 必须大于 0')
    return name, defaults


def calculate(frame, name, args=(), kwargs=None):
    name, p = parameters(name, args, kwargs or {})
    if frame.empty:
        return pd.DataFrame(columns=CATALOG[name]['outputs'], index=frame.index)
    valid = np.isfinite(frame[['open','high','low','close','volume']]).all(axis=1)
    if name == 'VWAP': valid &= np.isfinite(frame['amount'])
    if not valid.all():
        result = pd.DataFrame(np.nan, columns=CATALOG[name]['outputs'], index=frame.index)
        # A gap resets recursive indicator state. Re-warm on contiguous observed
        # bars, instead of carrying a made-up price or poisoning TA-Lib forever.
        for _, segment in frame.groupby((~valid).cumsum()):
            segment = segment.loc[valid.loc[segment.index]]
            if len(segment): result.loc[segment.index] = calculate(segment, name, kwargs=p)
        if name == 'VWAP':
            # Intraday cumulative price cannot restart mid-session after a gap.
            after_gap = (~valid).groupby(frame.index.normalize()).cummax()
            result.loc[after_gap, :] = np.nan
        return result
    if name not in CUSTOM:
        fn = abstract.Function(name)
        arrays = {c: frame[c].to_numpy(dtype=float) for c in ['open', 'high', 'low', 'close', 'volume']}
        try:
            outputs = fn(arrays, **p)
        except Exception as exc:
            raise ValueError(f'{name} 参数无效：{str(exc)[:140]}') from None
        if not isinstance(outputs, (list, tuple)):
            outputs = [outputs]
        return pd.DataFrame(dict(zip(fn.output_names, outputs)), index=frame.index)
    c, h, l, o, v = [frame[x] for x in ['close', 'high', 'low', 'open', 'volume']]
    n = p.get('n', 14)
    def divide(a, b):
        return a / b.replace(0, np.nan)
    def ma(x, window):
        return x.rolling(window).mean()
    if name == 'KDJ':
        low, high = l.rolling(n).min(), h.rolling(n).max()
        rsv = divide(c-low, high-low)*100
        # Explicit Chinese SMA(X,N,1), initialized with K=D=50.
        k, d = np.full(len(c), np.nan), np.full(len(c), np.nan)
        pk = pd_ = 50.
        for i, x in enumerate(rsv):
            if np.isfinite(x):
                pk += (x-pk)/p['m1']
                pd_ += (pk-pd_)/p['m2']
                k[i], d[i] = pk, pd_
        values = {'k': k, 'd': d, 'j': 3*k-2*d}
    elif name == 'BIAS':
        values = {'bias': divide(c-ma(c, n), ma(c, n))*100}
    elif name == 'BBI':
        values = {'bbi': sum(ma(c, p[x]) for x in ['n1', 'n2', 'n3', 'n4'])/4}
    elif name == 'DMI':
        values = {'pdi': talib.PLUS_DI(h, l, c, n), 'mdi': talib.MINUS_DI(h, l, c, n),
                  'adx': talib.ADX(h, l, c, n), 'adxr': talib.ADXR(h, l, c, n)}
    elif name == 'DMA':
        ddd = ma(c, p['fast'])-ma(c, p['slow'])
        values = {'ddd': ddd, 'ama': ma(ddd, p['m'])}
    elif name == 'PSY':
        psy = (c.diff()>0).astype(float).where(c.shift().notna()).rolling(n).sum()/n*100
        values = {'psy': psy, 'ma': ma(psy, p['m'])}
    elif name == 'VR':
        up, down, flat = [v.where(mask, 0).rolling(n).sum() for mask in [c>c.shift(), c<c.shift(), c==c.shift()]]
        values = {'vr': divide(up+flat/2, down+flat/2)*100}
    elif name == 'BRAR':
        values = {'br': divide((h-c.shift()).clip(lower=0).rolling(n).sum(), (c.shift()-l).clip(lower=0).rolling(n).sum())*100,
                  'ar': divide((h-o).rolling(n).sum(), (o-l).rolling(n).sum())*100}
    elif name == 'CR':
        mid = ((h+l)/2).shift()
        values = {'cr': divide((h-mid).clip(lower=0).rolling(n).sum(), (mid-l).clip(lower=0).rolling(n).sum())*100}
    elif name == 'EMV':
        raw = divide(((h+l)/2).diff()*(h-l), v)*1e8
        ev = ma(raw, n)
        values = {'emv': ev, 'ma': ma(ev, p['m'])}
    elif name == 'DPO':
        values = {'dpo': c.shift(n//2+1)-ma(c, n)}
    elif name == 'VWAP':
        values = {'vwap': divide(frame['amount'].groupby(frame.index.normalize()).cumsum(), v.groupby(frame.index.normalize()).cumsum())}
    elif name == 'DONCHIAN':
        upper, lower = h.rolling(n).max(), l.rolling(n).min()
        values = {'upper': upper, 'middle': (upper+lower)/2, 'lower': lower}
    elif name == 'KELTNER':
        middle = pd.Series(talib.EMA(c, n), index=c.index)
        atr = talib.ATR(h, l, c, p['atr_n'])*p['multiplier']
        values = {'upper': middle+atr, 'middle': middle, 'lower': middle-atr}
    elif name == 'SUPERTREND':
        atr = talib.ATR(h, l, c, n).to_numpy() if isinstance(talib.ATR(h,l,c,n), pd.Series) else talib.ATR(h,l,c,n)
        upper = ((h+l)/2).to_numpy()+p['multiplier']*atr
        lower = ((h+l)/2).to_numpy()-p['multiplier']*atr
        close = c.to_numpy()
        trend = np.full(len(c), np.nan)
        direction = np.full(len(c), np.nan)
        for i in range(n, len(c)):
            if i == n:
                trend[i], direction[i] = lower[i], 1
                continue
            upper[i] = upper[i] if upper[i]<upper[i-1] or close[i-1]>upper[i-1] else upper[i-1]
            lower[i] = lower[i] if lower[i]>lower[i-1] or close[i-1]<lower[i-1] else lower[i-1]
            direction[i] = (1 if close[i]>upper[i] else -1) if direction[i-1]<0 else (-1 if close[i]<lower[i] else 1)
            trend[i] = lower[i] if direction[i]>0 else upper[i]
        values = {'trend': trend, 'direction': direction}
    else:  # Wilder's swing index, cumulative ASI; limit is explicit and configurable.
        a, b, cc, d = (h-c.shift()).abs(), (l-c.shift()).abs(), (h-l).abs(), (c.shift()-o.shift()).abs()
        r = pd.Series(np.where((a>=b)&(a>=cc), a-b/2+d/4, np.where((b>a)&(b>=cc), b-a/2+d/4, cc+d/4)), index=c.index)
        swing = 50*divide(c-c.shift()+.5*(c-o)+.25*(c.shift()-o.shift()), r)*pd.concat([a,b],axis=1).max(axis=1)/p['limit']
        values = {'asi': swing.cumsum()}
    return pd.DataFrame(values, index=frame.index).replace([np.inf, -np.inf], np.nan)


def series(frame, name, args=(), kwargs=None, line=None):
    canonical = ALIASES.get(name.upper(), name.upper())
    result = calculate(frame, name, args, kwargs)
    line = LINES.get(canonical, {}).get(line, line) if line else result.columns[0]
    if line not in result:
        raise ValueError(f'{name} 输出应为：{", ".join(result.columns)}')
    return result[line]
