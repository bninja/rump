import json
import os
import StringIO
import time
import uuid

import pytest

from rump import Router, exc


def pytest_generate_tests(metafunc):
    if 'router_dynamic' in metafunc.fixturenames:
        name = 'test-{0}'.format(uuid.uuid4().hex)
        dynamics = []
        dynamics.append({
            '_type_': 'zookeeper',
            'hosts': ['localhost'],
            'timeout': 5,
            'root': '/{0}'.format(name),
        })
        dynamics.append({
            '_type_': 'redis',
            'key': 'rump-{0}'.format(name),
            'channel': 'rump-{0}'.format(name),
        })
        if os.getenv('RUMP_TEST_ETCD'):
            dynamics.append({
                '_type_': 'etcd',
                'key': '/rump/{0}'.format(name),
            })
        metafunc.parametrize('router_dynamic', dynamics)


@pytest.fixture
def router_name():
    return 'test-{0}'.format(uuid.uuid4().hex)


@pytest.fixture
def router(router_name, router_dynamic):
    return Router(
        name=router_name,
        enabled=True,
        hosts=['^veep\.it', '^api\.it'],
        compile_rules=True,
        auto_disable_rules=True,
        default_upstream='http://me',
        dynamic=router_dynamic,
        rules=[
            'client_ip4 in 1.2.3.4/32 => prod',
            'headers.x_1 in [1, 2, 4] => prod',
            'headers.x_2 = 3 => prod',
        ],
    )


def test_match_upstream_hit(router):
    content = json.dumps({'hi': 'there'})
    environ = {
        'REQUEST_METHOD': 'POST',
        'PATH_INFO': '/abc/123',
        'QUERY_STRING': 'a=b&c=d',
        'CONTENT_TYPE': 'application/json',
        'CONTENT_LENGTH': str(len(content)),
        'REMOTE_ADDR': '1.2.3.4',
        'wsgi.input': StringIO.StringIO(content),
    }
    req = router.request_type(environ)
    assert router.match_upstream(req) == router.upstream_parser('prod')


def test_match_upstream_miss(router):
    environ = {
        'REQUEST_METHOD': 'POST',
        'PATH_INFO': '/abc/123',
        'QUERY_STRING': 'a=b&c=d',
        'REMOTE_ADDR': '100.2.3.4',
        'CONTENT_TYPE': 'application/json',
    }
    req = router.request_type(environ)
    assert router.match_upstream(req) is router.default_upstream


def test_invalid_host_pattern(router_name):
    with pytest.raises(exc.InvalidField):
        Router(
            name='test-{0}'.format(uuid.uuid4().hex),
            hosts=['[<@'],
        )


def test_match_me_hit(router):
    hosts = [
        'veep.it.up', 'api.it.up',
    ]
    for host in hosts:
        environ = {
            'HTTP_HOST': host,
        }
        req = router.request_type(environ)
        assert router.match_me(req) is not None


def test_match_me_miss(router):
    environ = {
        'HTTP_HOST': 'null.it.up',
    }
    req = router.request_type(environ)
    assert router.match_me(req) is None

    req = router.request_type(environ)
    assert router.match_me(req) is None


def test_connect(router):
    assert not router.is_connected
    with router.connect():
        assert router.is_connected
    assert not router.is_connected


def test_load(router):
    with pytest.raises(exc.RouterNotConnected):
        router.load()
    with router.connect():
        router.load()


def test_save(router):
    with pytest.raises(exc.RouterNotConnected):
        router.save()
    assert router.compile_rules
    assert router.auto_disable_rules
    router_copy = type(router)(router)
    with router_copy.connect():
        router_copy.compile_rules = False
        router_copy.auto_disable_rules = False
        router_copy.save()
    with router.connect():
        assert router.compile_rules
        assert router.auto_disable_rules
        router.load()
        assert not router.compile_rules
        assert not router.auto_disable_rules


def test_watch(request, router):

    notifications = []
    notification_delay = 2.0
    router_copy = type(router)(router)
    router_copy.connect()
    request.addfinalizer(router_copy.disconnect)

    def _notify(router):
        notifications.append(1)
        router_copy.load()

    with pytest.raises(exc.RouterNotConnected):
        router.watch(_notify)

    with router.connect():
        router.watch(_notify)
        time.sleep(notification_delay)

        notification_count = sum(notifications)
        assert notification_count == 0
        assert router.compile_rules
        assert router_copy.compile_rules
        assert router.auto_disable_rules
        assert router_copy.auto_disable_rules
        assert router_copy.overrides == []

        router.compile_rules = False
        router.save()
        time.sleep(notification_delay)

        assert sum(notifications) > notification_count
        notification_count = sum(notifications)
        assert not router.compile_rules
        assert not router_copy.compile_rules
        assert router.auto_disable_rules
        assert router_copy.auto_disable_rules
        assert router_copy.overrides == []

        router.auto_disable_rules = False
        router.save()
        time.sleep(notification_delay)

        assert sum(notifications) > notification_count
        notification_count = sum(notifications)
        assert not router.compile_rules
        assert not router_copy.compile_rules
        assert not router.auto_disable_rules
        assert not router_copy.auto_disable_rules
        assert router_copy.overrides == []

        router.overrides.append('client_ip4 in 1.2.3.4/32 => prod')
        router.save()
        time.sleep(notification_delay)

        assert sum(notifications) > notification_count
        notification_count = sum(notifications)
        assert not router.compile_rules
        assert not router_copy.compile_rules
        assert not router.auto_disable_rules
        assert not router_copy.auto_disable_rules
        assert router_copy.overrides == [
            router.rule_parser('client_ip4 in 1.2.3.4/32 => prod')
        ]
