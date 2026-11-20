"""Monitoring worker, signal transitions and durable delivery queue."""
import json
import logging
import os
import smtplib
import threading
import time
from email.message import EmailMessage

import pandas as pd

from . import storage
from .market import DemoProvider, TushareProvider, now
from .public_market import PublicProvider, expected_end
from .rules import Evaluator
from .trading import trading_session

log = logging.getLogger(__name__)


class Monitor:
    def __init__(self):
        self.cache = {}
        self.errors = {}
        self.last_sync = None
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.thread = None
        self.screen_cache = None

    def market(self, symbol):
        source = storage.settings()['source']
        key = (source, symbol)
        with self.lock:
            item = self.cache.get(key)
            if item and time.monotonic()-item[0] < storage.settings()['interval']:
                return item[1]
            provider = {'demo': DemoProvider, 'tushare': TushareProvider, 'public': PublicProvider}[source]()
            market = provider.fetch(symbol)
            self.cache[key] = (time.monotonic(), market)
            if market.issues:
                self.errors[symbol] = '；'.join(market.issues)
            else:
                self.errors.pop(symbol, None)
            return market

    def current(self, market):
        if market.source == 'demo':
            return True
        if market.issues: return False
        # Require the latest expected CLOSED trading minute, with 2m provider grace.
        clock = now()
        calendar = market.calendar
        if calendar is None or not len(calendar): return False
        if market.calendar_until is not None and clock.normalize() > market.calendar_until: return False
        if market.source == 'public':
            for tf, frame in {'1m':market.minute, '1d':market.daily, **market.native}.items():
                expected = expected_end(clock-pd.Timedelta(minutes=2), calendar, tf)
                # Turnover can be absent on Sina daily bars. Price/volume rules
                # remain evaluable; expressions needing amount still get NaN.
                valid = frame.dropna(subset=['open','high','low','close','volume'])
                if expected is None or valid.empty or valid.index[-1] < expected: return False
            return True
        sessions = calendar[calendar <= clock.normalize()]
        if not len(sessions): return False
        day = sessions[-1]
        minute = clock.hour*60+clock.minute
        if day == clock.normalize() and minute < 571:
            if len(sessions)<2: return False
            expected = sessions[-2]+pd.Timedelta(hours=15)
        elif day == clock.normalize() and minute < 900:
            expected = day+pd.Timedelta(minutes=min(minute,690) if minute<781 else minute)
        else:
            expected = day+pd.Timedelta(hours=15)
        return len(market.minute)>0 and market.minute.index[-1] >= expected-pd.Timedelta(minutes=2)

    def record(self, rule, item, market, result):
        if (not result['ready'] or not self.current(market)
                or not self.session(market)['active']):
            return
        with storage.connect() as db:
            old = db.execute('SELECT matched FROM rule_state WHERE rule_id=? AND symbol=? AND source=?',
                             (rule['id'], item['symbol'], market.source)).fetchone()
            # New rules notify on the first known match; sustained matches do not repeat.
            if result['matched'] and (old is None or not old['matched']):
                key = f"{rule['id']}:{rule['version']}:{item['symbol']}:{market.source}:{result['bar_time']}"
                cursor = db.execute('''INSERT OR IGNORE INTO alerts
                    (rule_id,rule_name,symbol,name,source,bar_time,expression,evidence,event_key)
                    VALUES(?,?,?,?,?,?,?,?,?)''', (rule['id'], rule['name'], item['symbol'], item['name'], market.source,
                        result['bar_time'], rule['expression'], json.dumps(result['evidence']), key))
                if cursor.rowcount:
                    delivery = 'pending' if all(os.getenv(key) for key in ['SMTP_HOST','SMTP_FROM','ALERT_EMAIL']) else 'disabled'
                    db.execute('INSERT INTO outbox(alert_id,status) VALUES(?,?)', (cursor.lastrowid,delivery))
            db.execute('INSERT OR REPLACE INTO rule_state VALUES(?,?,?,?,?)',
                       (rule['id'], item['symbol'], market.source, int(result['matched']), result['bar_time']))

    def session(self, market=None):
        if market is not None:
            return trading_session(now(), market.source, market.calendar, market.calendar_until)
        source = storage.settings()['source']
        if source == 'public':
            rows = storage.rows('SELECT payload FROM market_cache WHERE source=? AND symbol=?', (source, '__calendar__'))
            if rows:
                days = pd.DatetimeIndex(json.loads(rows[0]['payload'])['days'])
                return trading_session(now(), source, days)
        for (cached_source, _), (_, data) in list(self.cache.items()):
            if cached_source == source:
                return self.session(data)
        return trading_session(now(), source)

    @staticmethod
    def applicable(rule, symbol):
        return rule['enabled'] and (not rule['symbols'] or symbol in rule['symbols'])

    def screen(self, refresh=False, record=False):
        """Saved-rule screening and alerts share evaluation, scope, and freshness.

        Reading/refreshing a screen never mutates alarm transition state. Only
        the worker records notifications, and only in a confirmed live session.
        """
        with self.lock:
            config = storage.settings()
            watchlist = storage.rows('SELECT * FROM watchlist')
            rules = [r for r in storage.rules() if r['enabled']]
            signature = json.dumps([config['source'], watchlist, rules], sort_keys=True)
            cached = self.screen_cache
            if not refresh and not record and cached and cached[0] == signature and time.monotonic()-cached[1] < config['interval']:
                session = self.session()
                return {**cached[2], 'session': session, 'reference_only': not session['active']}
            results = []
            for item in watchlist:
                applicable = [r for r in rules if self.applicable(r, item['symbol'])]
                row = {k:item[k] for k in ['symbol','name','kind']}
                row.update(rules=[], matched=False, status='no_rules', time=None)
                results.append(row)
                if not applicable and not record: continue
                market, error = None, None
                try:
                    market = self.market(item['symbol'])
                    row['time'] = str(market.minute.index[-1]) if len(market.minute) else None
                    if not self.current(market):
                        error = '；'.join(market.issues) or '行情缺失或落后于最近完成周期，已暂停判定'
                except Exception as exc:
                    error = str(exc)[:180]
                    log.warning('Data update failed for %s: %s', item['symbol'], type(exc).__name__)
                if error: self.errors[item['symbol']] = error
                if not applicable: continue  # worker still accumulates watchlist history
                for rule in applicable:
                    outcome = {'matched':False, 'ready':False, 'bar_time':None, 'evidence':{}, 'reason':error}
                    if not error:
                        try:
                            outcome = Evaluator(market).run(rule['expression'])
                        except Exception as exc:
                            outcome['reason'] = str(exc)[:180]
                    row['rules'].append({**{k:rule[k] for k in ['id','name','expression','symbols','version']}, **outcome})
                    if record and market is not None: self.record(rule, item, market, outcome)
                row['matched'] = any(r['matched'] and r['ready'] for r in row['rules'])
                row['status'] = 'matched' if row['matched'] else 'unknown' if any(not r['ready'] for r in row['rules']) else 'unmatched'
            session = self.session()
            summary = {'results':results, 'source':config['source'], 'asof':str(now()),
                       'session':session, 'reference_only':not session['active'], 'scanned':len(results),
                       'matched':sum(r['matched'] for r in results),
                       'unknown':sum(any(not x['ready'] for x in r['rules']) for r in results),
                       'no_rules':sum(r['status']=='no_rules' for r in results),
                       'enabled_rules':len(rules), 'interval':config['interval']}
            self.screen_cache = (signature, time.monotonic(), summary)
            return summary

    def tick(self):
        if not self.lock.acquire(blocking=False): return False
        try:
            self.screen(refresh=True, record=True)
            self.last_sync = str(now())
        finally:
            self.lock.release()
        self.deliver()
        return True

    def deliver(self):
        configured = all(os.getenv(key) for key in ['SMTP_HOST', 'SMTP_FROM', 'ALERT_EMAIL'])
        if not configured: return
        pending = storage.rows('''SELECT o.id AS queue_id,o.attempts,a.* FROM outbox o JOIN alerts a ON a.id=o.alert_id
            WHERE o.status='pending' AND o.retry_at<=? ORDER BY o.id LIMIT 10''', (time.time(),))
        for item in pending:
            message = EmailMessage()
            prefix = '[演示] ' if item['source']=='demo' else ''
            message['Subject'] = prefix+item['rule_name']+' · '+item['name']
            message['From'], message['To'] = os.environ['SMTP_FROM'], os.environ['ALERT_EMAIL']
            message.set_content(f"{item['name']} {item['symbol']}\n{item['rule_name']}\nK线时间：{item['bar_time']}\n{item['expression']}\n数据源：{item['source']}\n\n{item['evidence']}")
            try:
                with smtplib.SMTP_SSL(os.environ['SMTP_HOST'], int(os.getenv('SMTP_PORT','465')), timeout=10) as smtp:
                    if os.getenv('SMTP_USER'): smtp.login(os.environ['SMTP_USER'], os.getenv('SMTP_PASSWORD',''))
                    smtp.send_message(message)
                with storage.connect() as db:
                    db.execute("UPDATE outbox SET status='sent',error=NULL WHERE id=?", (item['queue_id'],))
            except Exception:
                count = item['attempts']+1
                with storage.connect() as db:
                    db.execute("UPDATE outbox SET attempts=?,retry_at=?,status=?,error=? WHERE id=?",
                               (count,time.time()+min(3600,30*2**min(count,7)), 'failed' if count>=6 else 'pending',
                                '邮件发送失败，请检查 SMTP 配置或网络',item['queue_id']))

    def start(self):
        def work():
            while not self.stop.is_set():
                try: self.tick()
                except Exception: log.exception('Monitor cycle failed')
                interval = storage.settings().get('interval',60)
                next_run = (int(time.time())//interval+1)*interval+3
                self.stop.wait(max(.1,next_run-time.time()))
        self.thread = threading.Thread(target=work, name='market-monitor', daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread: self.thread.join(timeout=3)
