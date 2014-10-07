import base64
import json
import StringIO

import pilo
import pytest

from rump import Request, types, parser, and_, or_, request, exp, exc


def test_map():
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
    req = Request(environ)
    assert req.method == 'POST'
    assert req.path == '/abc/123'
    assert req.query_string == 'a=b&c=d'
    assert req.query == {'a': 'b', 'c': 'd'}
    assert req.has_content
    assert req.content_length == len(content)
    assert req.content == content
    assert not req.authenticated
    assert req.client_ip4 == types.IPAddress('1.2.3.4')


def test_headers():
    environ = {
        'REQUEST_METHOD': 'GET',
        'PATH_INFO': '/abc/123',
        'QUERY_STRING': 'a=b&c=d',
        'HTTP_X_1': '1',
        'HTTP_X_2': '22',
        'HTTP_X_3': '333',
        'HTTP_X_4': '4444',
    }
    req = Request(environ)
    assert req.headers == {
        'http_x_1': '1',
        'http_x_2': '22',
        'http_x_3': '333',
        'http_x_4': '4444',
    }
    assert not req.has_content


def test_basic_authorization():
    username, password = 'mellow', 'there'
    value = 'Basic {0}'.format(
        base64.encodestring('{0}:{1}'.format(username, password))
    )
    environ = {
        'REQUEST_METHOD': 'GET',
        'PATH_INFO': '/abc/123',
        'QUERY_STRING': 'a=b&c=d',
        'HTTP_AUTHORIZATION': value,
    }
    req = Request(environ)
    assert req.authenticated
    assert req.basic_authorization == {
        'username': username, 'password': password
    }
    assert req.username == username
    assert req.password == password


def test_invalid_basic_authorization():
    environ = {
        'REQUEST_METHOD': 'GET',
        'PATH_INFO': '/abc/123',
        'QUERY_STRING': 'a=b&c=d',
        'HTTP_AUTHORIZATION': '@!#!@#!#$',
    }
    req = Request(environ)
    assert req.authenticated
    assert req.basic_authorization is None
    assert req.username is None
    assert req.password is None


def test_request_ctx():
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
    ctx = Request(environ).context(exp.Symbols())
    assert ctx['request'][Request.method] == 'POST'
    assert ctx['request'][Request.path] == '/abc/123'
    assert ctx['request'][Request.query_string] == 'a=b&c=d'
    assert ctx['request'][Request.query] == {'a': 'b', 'c': 'd'}
    assert ctx['request'][Request.has_content]
    assert ctx['request'][Request.content_length] == len(content)
    assert ctx['request'][Request.content] == content
    assert not ctx['request'][Request.authenticated]
    assert ctx['request'][Request.client_ip4] == types.IPAddress('1.2.3.4')


@pytest.fixture
def parse_match():
    return parser.for_match(Request)


def test_match_unsupported_type():

    class MyField(pilo.Field, request.PathMixin):

        type = float

    class MyRequest(Request):

        nope = MyField()

    parse_match = parser.for_match(MyRequest)
    cases = [
        ('nope = 0.1', exc.ParseException),
    ]
    for raw, ex in cases:
        with pytest.raises(ex):
            parse_match(raw)
    cases = [
        ('headers.x_test ~ "1"', Request.headers.x_test.match('1')),
        ('X-Test in headers', Request.headers.contains('X-Test')),
    ]
    for raw, expr in cases:
        parsed = parse_match(raw)
        assert expr == parsed


def test_match_header_hash(parse_match):
    cases = [
        ('headers.x_test ~ "1"', Request.headers.x_test.match('1')),
        ('X-Test in headers', Request.headers.contains('X-Test')),
    ]
    for raw, expr in cases:
        parsed = parse_match(raw)
        assert expr == parsed


def test_match_arg_hash(parse_match):
    cases = [
        ('query.something ~ "1"', Request.query.something.match('1')),
        ('something in query', Request.query.contains('something')),
    ]
    for raw, expr in cases:
        parsed = parse_match(raw)
        assert expr == parsed


def test_match_valid(parse_match):
    cases = [
        ('client_ip4 in 1.2.3.4/32',
         Request.client_ip4.in_(types.IPNetwork('1.2.3.4/32'))
         ),
        ('method in [GET, POST] or client_ip4 in 1.2.3.4/32',
         or_(Request.method.in_(['GET', 'POST']),
             Request.client_ip4.in_(types.IPNetwork('1.2.3.4/32')))),
        ('method != PATCH and path startswith peep',
         and_(Request.method != "PATCH",
              Request.path.startswith('peep'))),
        ('content_length >= 123',
         Request.content_length >= 123),
        ('content_length != -123',
         Request.content_length != -123),
        ('"TEST" in path',
         Request.path.contains("TEST")),
        ('"TEST" not in path',
         ~ Request.path.contains("TEST")),
        ('query.something ~ "\d{1,3}"',
         Request.query.something.match('\d{1,3}')),
        ("query.something ~ '\d{1,3}'",
         Request.query.something.match('\d{1,3}')),
        ('basic_authorization.username = karlito',
         Request.basic_authorization.username == 'karlito'),
        ('basic_authorization.username != notsosecret',
         Request.basic_authorization.username != 'notsosecret'),
    ]
    for raw, expr in cases:
        parsed = parse_match(raw)
        assert expr == parsed


def test_match_invalid(parse_match):
    cases = [
        ('client_ip4 in abc', exc.ParseException),
        ('client_ip4 startswith abc', exc.ParseException),
        ('method > "GET"', exc.ParseException),
        ('method = "GET" maybe not', exc.ParseException),
        ('query.something ~ "[)()"', exc.ParseException),
        ('query.something !~ "[)()"', exc.ParseException),
    ]
    for raw, ex in cases:
        with pytest.raises(ex):
            parse_match(raw)


def test_match_null(parse_match):
    cases = [
        ('client_ip4 = null',
         Request.client_ip4 == None),
        ('client_ip4 != null',
         Request.client_ip4 != None),
        ('method = null',
         Request.method == None),
        ('method != null',
         Request.method != None),
        ('has_content = null',
         Request.has_content == None),
        ('has_content != null',
         Request.has_content != None),
    ]
    for raw, expected in cases:
        parsed = parse_match(raw)
        assert expected == parsed
