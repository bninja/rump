import os
import threading
import uuid
import wsgiref.simple_server

import pytest
import requests

from rump import wsgi, __version__


@pytest.fixture
def settings():
    return {
        'id_header': 'X-Test-Id',
        'health_file': os.path.abspath(__file__),
        'routers': [
            {
                'name': 'one',
                'hosts': ['one\.me\.com'],
                'rules': [
                    'method = GET => http://cache.one.internal.com',
                ]
            },
            {
                'name': 'two',
                'hosts': ['(one|two)\.me\.com'],
                'rules': [
                    'method = GET => http://cache.two.internal.com',
                ]
            },
            {
                'name': 'three',
                'hosts': ['\d{1,3}\.me\.net'],
                'rules': [
                    'method = GET => http://cache.two.internal.com',
                ]
            },
        ],
    }


@pytest.fixture
def server(request, settings):
    wsgi.app.settings.map(settings)
    server = wsgiref.simple_server.make_server('localhost', 0, wsgi.app)
    thd = threading.Thread(target=server.serve_forever)
    thd.start()
    request.addfinalizer(server.shutdown)
    return 'http://{0}:{1}'.format(*server.server_address)


def test_health(server):
    resp = requests.get(server + '/health')
    assert resp.status_code == 200


def test_boom(server):
    resp = requests.get(server + '/boom')
    assert resp.status_code == 500


def test_select_no_router(server):
    resp = requests.get(
        server + '/yabba/dabba?doo=dle',
        headers={
            'Host': 'hi.ppo.com',
        }
    )
    assert resp.status_code == 500


def test_select_no_upstrem(server):
    resp = requests.post(
        server + '/yabba/dabba?doo=dle',
        headers={
            'Host': 'one.me.com',
        }
    )
    assert resp.status_code == 500


def test_select_xaccel(server):
    id = uuid.uuid4().hex
    resp = requests.get(
        server + '/yabba/dabba?doo=dle',
        headers={
            'Host': 'one.me.com',
            'X-Test-Id': id,
        }
    )
    assert resp.status_code == 200
    headers = resp.headers.copy()
    headers.pop('server')
    headers.pop('date')
    assert headers == {
        'content-length': '0',
        'x-rump-forward': 'http://cache.one.internal.com',
        'x-rump-redir-host': 'cache.one.internal.com',
        'x-rump-redir-proto': 'http',
        'x-accel-redirect': '/rump/yabba/dabba?doo=dle',
        'x-rump-host': wsgi.app.host,
        'x-rump-version': __version__,
        'x-test-id': id,
    }


def test_select_xaccel_default_upstream(server):
    resp = requests.patch(
        server + '/yabba/dabba?doo=dle',
        headers={
            'Host': 'one.me.com',
            'X-Rump-Redir-Default': 'https://dev.here.com',
        }
    )
    assert resp.status_code == 200
    headers = resp.headers.copy()
    headers.pop('server')
    headers.pop('date')
    assert headers == {
        'content-length': '0',
        'x-rump-forward': 'https://dev.here.com',
        'x-rump-redir-host': 'dev.here.com',
        'x-rump-redir-proto': 'https',
        'x-accel-redirect': '/rump/yabba/dabba?doo=dle',
        'x-rump-host': wsgi.app.host,
        'x-rump-version': __version__
    }


def test_select_xaccel_echo(server):
    resp = requests.get(
        server + '/yabba/dabba?doo=dle',
        headers={
            'Host': 'one.me.com',
            'X-Rump-Echo': '1',
        }
    )
    assert resp.status_code == 200
    headers = resp.headers.copy()
    headers.pop('server')
    headers.pop('date')
    assert headers == {
        'content-length': '25',
        'x-rump-forward': 'http://cache.one.internal.com',
        'x-rump-redir-host': 'cache.one.internal.com',
        'content-type': 'text/plain',
        'x-rump-redir-proto': 'http',
        'x-rump-host': wsgi.app.host,
        'x-rump-version': __version__
    }
    assert resp.content == '/rump/yabba/dabba?doo=dle'
