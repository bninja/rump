import json
import StringIO

import mock
import pytest

from rump import (
    parser, Upstream, Selection, Server, Request, types, Rule, Rules, exc
)


@pytest.fixture
def parse_rule():
    return parser.for_rule(Request)


def test_rule_valid(parse_rule):
    cases = [(
        'client_ip4 in 1.2.3.4/32 => prod',
        Rule(
            Request.client_ip4.in_(types.IPNetwork('1.2.3.4/32')),
            Upstream(Selection(Server('http', 'prod'), 1))
        ),
    )]
    for raw, expected in cases:
        parsed = parse_rule(raw)
        assert expected == parsed


def test_rule_invalid(parse_rule):
    cases = [
        ('client_ip4 in 1.2.3.4/32 => prod,wat', exc.ParseException),
        ('client !in 1.2.3.4/32 => prod', exc.ParseException),
    ]
    for raw, ex in cases:
        with pytest.raises(ex):
            parse_rule(raw)


def test_rule_match(parse_rule):
    content = json.dumps({'hi': 'there'})
    req = Request(environ={
        'METHOD': 'PATCH',
        'REMOTE_ADDR': '1.2.3.4',
        'PATH_INFO': '/a/b/c/123',
        'HTTP_X_1': '5',
        'CONTENT_TYPE': 'application/json',
        'CONTENT_LENGTH': str(len(content)),
        'wsgi.input': StringIO.StringIO(content),
    })
    cases = [
        ('client_ip4 in 1.2.3.4/32 => prod', True),
        ('headers.x_1 in [1, 2, 4] => prod', False),
        ('headers.x_1 !in [1, 2, 4] => prod', True),
        ('headers.x_2 = 3 => prod', False),
        ('content_length >= 10 => prod', True),
        ('content_length > 10 => prod', True),
        ('content_length < 10 => prod', False),
        ('content_length <= 10 => prod', False),
        ('content_length = 15 => prod', True),
        ('content_length != 15 => prod', False),
        ('has_content => prod', True),
        ('!has_content => prod', False),
        ('"a/b" in path => prod', True),
        ('"b/a" in path => prod', False),
        ('"b/a" !in path => prod', True),
        ('path startswith "/a/b/c" => prod', True),
        ('path endswith 123 => prod', True),
        ('"/b/" in path => prod', True),
        ('"/veep/" in path => prod', False),
        ('path ~ "/(\w/){3}123" => prod', True),
        ('path !~ "/(\w/){3}123" => prod', False),
    ]
    for case, expected in cases:
        r = parse_rule(case)
        assert r.expression(req) == expected


@pytest.fixture
def rules():
    return [
        Rule(
            Request.client_ip4.in_(types.IPNetwork('1.2.3.4/32')),
            Upstream(Selection(Server('http', 'me'), 1))
        ),
        Rule(
            Request.method.in_(['GET', 'POST']),
            Upstream(
                Selection(Server('https', 'prod1'), 1),
                Selection(Server('https', 'prod2'), 12),
            )
        ),
    ]


def test_rules_load(rules):
    raw = '\n'.join([str(rule) for rule in rules])
    assert Rules().loads(raw) == rules


def test_rules_load_parse_error(rules):
    raw = '\n'.join([str(rule) for rule in rules] + ['junk'])
    assert Rules(strict=False).loads(raw) == rules
    with pytest.raises(exc.ParseException):
        Rules().loads(raw)
    assert Rules().loads(raw, strict=False) == rules
    with pytest.raises(exc.ParseException):
        Rules().loads(raw, strict=True)


def test_rules_dump(rules):
    raw = '\n'.join([str(rule) for rule in rules])
    assert Rules(rules).dumps().strip() == raw.strip()


def test_rules_match_miss(rules):
    req = Request(environ={
        'REQUEST_METHOD': 'PATCH',
        'REMOTE_ADDR': '11.22.33.44',
    })
    rules = Rules(rules)
    assert rules.match(req) is None
    rules.compile = True
    assert rules.match(req) is None
    rules.compile = False
    assert rules.match(req) is None


def test_rules_match_hit(rules):
    req = Request(environ={
        'REQUEST_METHOD': 'PATCH',
        'REMOTE_ADDR': '1.2.3.4',
    })
    rules = Rules(rules)
    assert str(rules.match(req)) == 'http://me,1'
    rules.compile = True
    assert str(rules.match(req)) == 'http://me,1'
    rules.compile = False
    assert str(rules.match(req)) == 'http://me,1'


def test_rules_enable_disable(rules):
    rules = Rules(rules)
    assert rules.disabled == set()
    with pytest.raises(IndexError):
        rules.disable(100)
    rules.disable(1)
    assert rules.disabled == set([rules[1]])
    assert rules[1] in rules.disabled
    rules.enable(1)
    assert rules.disabled == set()
    rules.disable_all()
    assert rules.disabled == set(rules)
    rules.enable_all()
    assert rules.disabled == set()


def test_rules_match_error_propagate(rules):
    req = Request(environ={
        'REQUEST_METHOD': 'PATCH',
        'REMOTE_ADDR': '1.2.3.4',
    })

    rs = Rules(rules, compile=False)
    with mock.patch('rump.Rule.match') as patch:
        patch.side_effect = Exception('boom')
        with pytest.raises(Exception):
            rs.match(req, error='raise')
    assert all(rule not in rs.disabled for rule in rs)

    rs = Rules(rules, compile=True)
    with mock.patch('rump.Rule.compiled_type.match') as patch:
        patch.side_effect = Exception('boom')
        rs.match(req, error='disable')
    assert all(rule not in rs.disabled for rule in rs)


def test_rules_match_error_disable(rules):
    req = Request(environ={
        'REQUEST_METHOD': 'PATCH',
        'REMOTE_ADDR': '1.2.3.4',
    })

    rs = Rules(rules, compile=False)
    with mock.patch('rump.Rule.match') as patch:
        patch.side_effect = Exception('boom')
        rs.match(req, error='disable')
    assert all(rule in rs.disabled for rule in rs)

    rs = Rules(rules, compile=True)
    with mock.patch('rump.rule.CompiledRule.match_context') as patch:
        patch.side_effect = Exception('boom')
        rs.match(req, error='disable')
    assert all(rule in rs.disabled for rule in rs)
