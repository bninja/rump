import json
import threading

import mock
import pytest
import requests
import time

from rump import dumps, cli, Settings


@pytest.fixture
def config_path(request):
    return request.config.fixtures_path.join('settings', 'main.conf')


@pytest.fixture
def requests_path(request):
    return request.config.fixtures_path.join('requests')


@pytest.fixture
def parser(config_path):
    return cli.parser(conf_file=str(config_path))


@pytest.fixture
def settings(config_path):
    return Settings.from_file(str(config_path))


def test_list(capsys, parser):
    args = parser.parse_args(['list'])
    cli.setup(args)
    args.command(args)
    out, err = capsys.readouterr()
    assert out == '\n'.join([
        'router1',
        'router2',
        'router3',
        '',
    ])
    assert err == ''


def test_show(capsys, parser):
    args = parser.parse_args(['show', 'router1'])
    cli.setup(args)
    args.command(args)
    out, err = capsys.readouterr()
    assert out == dumps(args.settings.routers[0]) + '\n'
    assert err == ''


def test_check(capsys, parser):
    args = parser.parse_args(['check', 'router1'])
    cli.setup(args)
    rc = args.command(args)
    assert rc == 0
    out, err = capsys.readouterr()
    assert out == ''
    assert err == ''


def test_edit(tmpdir, parser):
    path = tmpdir.join('edit1.json')
    path.write(data=json.dumps({'compile_rules': False}), ensure=True)
    args = parser.parse_args(['edit', 'router2', str(path)])
    cli.setup(args)
    args.command(args)

    path = tmpdir.join('edit2.json')
    path.write(data=json.dumps({'compile_rules': True}), ensure=True)
    args = parser.parse_args(['edit', 'router2', str(path)])
    cli.setup(args)
    args.command(args)


def test_watch(capsys, tmpdir, parser):

    def _watch():
        args = parser.parse_args(['watch', 'router2', '-n', '1', '-t', '10'])
        cli.setup(args)
        args.command(args)

    thd = threading.Thread(target=_watch)
    thd.start()
    time.sleep(1.0)

    path = tmpdir.join('edit1.json')
    path.write(data=json.dumps({'compile_rules': False}), ensure=True)
    args = parser.parse_args(['edit', 'router2', str(path)])
    cli.setup(args)
    args.command(args)

    thd.join()

    out, _ = capsys.readouterr()
    assert out == 'router changed - router2\n'


def test_eval(capsys, tmpdir, parser, requests_path):
    requests = tmpdir.join('requests.http')
    for request_path in requests_path.listdir():
        requests.write(request_path.read(), ensure=True)
    args = parser.parse_args(['eval', '-r', str(requests)])
    cli.setup(args)
    args.command(args)
    out, _ = capsys.readouterr()
    assert out == '\n'.join([
        'https://www.google.com',
        'https://www.yahoo.com',
        'http://dev.google.com',
        '',
    ])


def test_serve(parser, settings):

    def _serve():
        args = parser.parse_args(['serve'])
        cli.setup(args)
        with mock.patch('rump.cli.server_for') as patched:
            patched.return_value = server
            args.command(args)

    server = cli.server_for(host='localhost', port=0, mode=None)
    thd = threading.Thread(target=_serve)
    thd.daemon = True
    thd.start()
    time.sleep(1.0)

    try:
        root = 'http://{0}:{1}'.format(*server.server_address)

        for case in [
                {
                    'path': '/1/a',
                    'headers': {'Host': 'google.example.com'},
                    'x-rump-forward': 'https://www.google.com',
                    'x-rump-redir-proto': 'https',
                    'x-rump-redir-host': 'www.google.com',
                }, {
                    'path': '/2/b',
                    'headers': {'Host': 'yahoo.example.com'},
                    'x-rump-forward': 'https://www.yahoo.com',
                    'x-rump-redir-proto': 'https',
                    'x-rump-redir-host': 'www.yahoo.com',
                }, {
                    'path': '/3/c',
                    'headers': {'Host': 'dev.google.com'},
                    'x-rump-forward': 'http://dev.google.com',
                    'x-rump-redir-proto': 'http',
                    'x-rump-redir-host': 'dev.google.com',
                },
            ]:
            resp = requests.get(root + case['path'], headers=case['headers'])

            assert resp.status_code == 200

            assert 'x-rump-forward' in resp.headers
            assert resp.headers['x-rump-forward'] == case['x-rump-forward']
            assert 'x-rump-redir-proto' in resp.headers
            assert resp.headers['x-rump-redir-proto'] == case['x-rump-redir-proto']
            assert 'x-rump-redir-host' in resp.headers
            assert resp.headers['x-rump-redir-host'] == case['x-rump-redir-host']
    finally:
        server.shutdown()
        thd.join()
