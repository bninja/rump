import mock
import pytest

from rump import parser, Server, Upstream, Selection, exc


@pytest.fixture
def parse():
    return parser.for_upstream()


def test_upstream_valid(parse):
    cases = [
        ('hi',
         Upstream(Selection(Server('http', 'hi'), 1))),
        ('https://hi',
         Upstream(Selection(Server('https', 'hi'), 1))),
        ('https://hi,23',
         Upstream(Selection(Server('https', 'hi'), 23))),
        ('https://hi,23 http://there/you,33 bye',
         Upstream([
            Selection(Server('https', 'hi'), 23),
            Selection(Server('http', 'there/you'), 33),
            Selection(Server('http', 'bye'), 1),
         ])),
    ]
    for raw, expected in cases:
        parsed = parse(raw)
        assert expected == parsed


def test_upstream_invalid(parse):
    cases = [
        ('hi,nope', exc.ParseException),
        ('hi,-1', exc.ParseException),
        ('', exc.ParseException),
    ]
    for raw, ex in cases:
        with pytest.raises(ex):
            parse(raw)


def test_upstream_select(parse):
    upstream = parse('http://1:81,1 http://2:82,5 https://4:84,3')
    assert not upstream.uniform
    servers = [selection.server for selection in upstream]
    for _ in xrange(20):
        server = upstream()
        assert server in servers


def test_upstream_select_uniform(parse):
    upstream = parse('http://1:81 http://2:82 https://4:84')
    assert [
            Server('http', '1:81'),
            Server('http', '2:82'),
            Server('https', '4:84')
        ] == upstream.servers
    assert upstream.uniform
    servers = [selection.server for selection in upstream]
    for _ in xrange(20):
        server = upstream()
        assert server in servers


def test_upstream_select_impossible(parse):
    upstream = parse('http://1:81,1 http://2:825 https://4:84,3')
    with mock.patch('rump.upstream.random.randint') as randint:
        randint.return_value = upstream.total
        with pytest.raises(Exception):
            upstream()
        randint.return_value = upstream.total - 1
        upstream()
