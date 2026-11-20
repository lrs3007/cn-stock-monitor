import time

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.mobile import COOKIE, MAX_BODY, access_key, allowed_host, create_app, session_token, valid_session

KEY = 'test-pairing-key-with-at-least-32-characters'


@pytest.fixture
def mobile():
    app = create_app(key=KEY, upstream='http://127.0.0.1:8787')
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={'path': request.url.path, 'query': str(request.url.query)},
                              headers={'Cache-Control': 'max-age=300'})

    with TestClient(app, base_url='http://192.168.1.8:8788') as client:
        original = app.state.client
        app.state.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        yield client, seen
        client.portal.call(app.state.client.aclose)
        app.state.client = original


def pair(client):
    response = client.post('/connect', json={'key': KEY})
    assert response.status_code == 200
    return response


def test_gateway_denies_unpaired_api_and_static(mobile):
    client, seen = mobile
    for path in ('/', '/api/status', '/api/watchlist', '/app.js', '/docs'):
        assert client.get(path).status_code == 401
    result = client.get('/', headers={'Accept': 'text/html'}, follow_redirects=False)
    assert result.status_code == 303 and result.headers['location'] == '/connect'
    assert client.get('/connect').status_code == 200
    assert seen == []


def test_pair_cookie_proxy_and_logout(mobile):
    client, seen = mobile
    response = pair(client)
    cookie = response.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'SameSite=strict' in cookie and KEY not in cookie
    assert client.get('/api/rules?symbol=510300.SH').status_code == 200
    assert client.post('/api/rules', json={'name': '个性化规则'}).status_code == 200
    assert seen[-1].url.host == '127.0.0.1'
    assert 'cookie' not in seen[-1].headers and 'origin' not in seen[-1].headers
    assert '个性化规则' in seen[-1].content.decode()
    assert client.get('/app.js').headers['cache-control'] == 'no-store'
    assert client.post('/disconnect', json={}).status_code == 200
    assert client.get('/api/status').status_code == 401


def test_session_tamper_expiry_and_key_rotation():
    token = session_token(KEY)
    assert valid_session(KEY, token)
    assert not valid_session('new-key', token)
    assert not valid_session(KEY, token[:-1] + ('0' if token[-1] != '0' else '1'))
    assert not valid_session(KEY, session_token(KEY, int(time.time()) - 1))
    for value in (None, '', 'bad', 'x' * 9999, 'abc.def.ghi'):
        assert not valid_session(KEY, value)


def test_rate_limit_and_invalid_json(mobile):
    client, _ = mobile
    assert client.post('/connect', content='[]', headers={'Content-Type': 'application/json'}).status_code == 401
    for _ in range(4):
        assert client.post('/connect', json={'key': 'wrong'}).status_code == 401
    assert client.post('/connect', json={'key': KEY}).status_code == 429


def test_gateway_rejects_bad_origin_host_and_large_body(mobile):
    client, seen = mobile
    assert client.post('/connect', json={'key': KEY}, headers={'Origin': 'https://evil.example'}).status_code == 403
    assert client.post('/connect', data={'key': KEY}).status_code == 415
    assert client.get('/connect', headers={'Host': 'evil.example'}).status_code == 400
    pair(client)
    assert client.delete('/api/rules/1', headers={'Origin': 'https://evil.example'}).status_code == 403
    assert client.post('/api/rules', content='x' * (MAX_BODY + 1), headers={'Content-Type': 'application/json'}).status_code == 413
    assert seen == []


def test_proxy_fixed_destination_and_query(mobile):
    client, seen = mobile
    pair(client)
    client.get('/%2F%2Fevil.example/api?q=http://evil.example')
    assert seen[-1].url.host == '127.0.0.1'
    assert seen[-1].url.query == b'q=http://evil.example'


def test_key_persisted_private(tmp_path, monkeypatch):
    path = tmp_path / 'mobile-key.secret'
    monkeypatch.setenv('MONITOR_MOBILE_KEY_FILE', str(path))
    key = access_key()
    assert len(key) >= 32 and access_key() == key
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('host', ['localhost', '127.0.0.1', '192.168.1.5', '10.1.2.3', '172.31.255.254'])
def test_local_hosts_allowed(host):
    assert allowed_host(host)


@pytest.mark.parametrize('host', ['example.com', '192.168.1.1.evil.com', '172.32.0.1', '8.8.8.8', '0.0.0.0', '169.254.169.254'])
def test_unknown_hosts_blocked(host):
    assert not allowed_host(host)


def test_https_cookie_is_secure():
    with TestClient(create_app(key=KEY), base_url='https://192.168.1.8:8788') as client:
        assert 'Secure' in pair(client).headers['set-cookie']


def test_apk_download_exposes_only_fixed_artifact(tmp_path, monkeypatch):
    from backend import mobile
    monkeypatch.setattr(mobile, 'ROOT', tmp_path)
    with TestClient(create_app(key=KEY), base_url='http://127.0.0.1:8788') as client:
        assert client.get('/download/guanlan.apk').status_code == 404
        apk = tmp_path / 'dist/android/guanlan-0.3.1.apk'
        apk.parent.mkdir(parents=True)
        apk.write_bytes(b'test apk bytes')
        result = client.get('/download/guanlan.apk')
        assert result.status_code == 200 and result.content == b'test apk bytes'
        assert result.headers['content-type'] == 'application/vnd.android.package-archive'
        assert client.get('/download/signing.properties').status_code == 401


def test_upstream_redirect_stays_on_gateway(mobile):
    client, _ = mobile
    pair(client)
    async def redirect(*args, **kwargs):
        return httpx.Response(307, headers={'Location': 'http://127.0.0.1:8787/api/rules'})
    client.app.state.client.request = redirect
    result = client.get('/api/rules/', follow_redirects=False)
    assert result.headers['location'] == '/api/rules'
