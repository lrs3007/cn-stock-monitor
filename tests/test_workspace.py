from fastapi.testclient import TestClient
from backend.main import app


def test_merge_is_validated_atomic_and_repeatable(store):
    client = TestClient(app)
    before = client.get('/api/workspace/export').json()
    assert before['format'] == 'guanlan-workspace-v1'
    assert client.post('/api/workspace/import', json=before).json() == {'watchlist_added':0, 'rules_added':0}
    data = {'format':before['format'], 'watchlist':[{'symbol':'512880.SH'}],
            'rules':[{'name':'证券ETF专属', 'expression':'RSI(14) < 30', 'symbols':['512880.SH'], 'enabled':True}]}
    assert client.post('/api/workspace/import',json=data).json() == {'watchlist_added':1,'rules_added':1}
    assert client.post('/api/workspace/import',json=data).json() == {'watchlist_added':0,'rules_added':0}
    after = client.get('/api/workspace/export').json()
    invalid = {**data, 'watchlist':[{'symbol':'510050.SH'}], 'rules':[dict(data['rules'][0],expression='__import__("os")')]}
    assert client.post('/api/workspace/import',json=invalid).status_code == 400
    assert client.get('/api/workspace/export').json() == after
    assert 'TUSHARE' not in str(after)


def test_invalid_format_and_limit(store):
    client = TestClient(app)
    assert client.post('/api/workspace/import',json={'format':'other'}).status_code == 422
    assert client.post('/api/workspace/import',json={'format':'guanlan-workspace-v1','rules':[{}]*101}).status_code == 422


def test_import_limit_counts_existing_duplicate_rows(store):
    with store.connect() as db:
        db.executemany('INSERT INTO rules(name,expression,symbols,enabled) VALUES(?,?,?,?)',
                       [('重复规则','RSI(14)>50','[]',1)]*97)
    client = TestClient(app)
    data={'format':'guanlan-workspace-v1','rules':[{'name':'新增规则','expression':'RSI(14)>60','symbols':[],'enabled':True}]}
    assert client.post('/api/workspace/import',json=data).status_code == 400
    assert len(store.rules()) == 100
