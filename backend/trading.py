"""Cash-market monitoring sessions; exchange dates, Shanghai local timestamps.

The minute stamped 11:30 / 15:00 is evaluated once it closes. Opening auction
and after-hours fixed-price trading are outside this minute-bar monitor.
"""
import pandas as pd


def trading_session(clock, source, calendar=None, calendar_until=None):
    result = {'active': False, 'phase': 'unknown', 'label': '交易日历待确认',
              'server_time': str(clock), 'next_open': None, 'timezone': 'Asia/Shanghai'}
    if source == 'demo':
        return {**result, 'active': True, 'phase': 'demo', 'label': '演示运行 · 非实盘'}
    if calendar is None or not len(calendar): return result
    calendar = pd.DatetimeIndex(calendar).normalize().unique().sort_values()
    until = calendar_until if calendar_until is not None else calendar[-1]
    day = clock.normalize()
    if day < calendar[0] or day > until: return result
    tomorrow = calendar[calendar > day]
    if len(tomorrow): result['next_open'] = str(tomorrow[0] + pd.Timedelta(hours=9, minutes=30))
    if day not in calendar:
        return {**result, 'phase': 'holiday', 'label': '非交易日'}
    minute = clock.hour*60 + clock.minute
    if 570 <= minute <= 690 or 780 <= minute <= 900:
        label = '收盘确认' if minute == 900 else '午间收盘确认' if minute == 690 else '交易中'
        return {**result, 'active': True, 'phase': 'trading', 'label': label, 'next_open': None}
    if minute < 570:
        return {**result, 'phase': 'preopen', 'label': '未开盘',
                'next_open': str(day+pd.Timedelta(hours=9, minutes=30))}
    if minute < 780:
        return {**result, 'phase': 'lunch', 'label': '午间休市', 'next_open': str(day+pd.Timedelta(hours=13))}
    return {**result, 'phase': 'closed', 'label': '已收盘'}
