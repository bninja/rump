"""
"""
from .. import Rule, Request, Upstream
from . import match, upstream, rule


__all__ = [
    'for_rule',
    'for_match',
    'for_rule',
    'ParseException',
]


def for_rule(request_type=None, upstream_aliases=None, rule_type=None):
    """
    :param request_type:
    :param upstream_aliases:
    :param rule_type:

    :return:
    """

    def _parse(raw):
        result = g.parseString(raw, parseAll=True)
        rule = rule_type(result.match, result.upstream)
        return rule

    rule_type = rule_type or Rule
    request_type = request_type or Request
    g = rule.grammar_for(request_type.fields, upstream_aliases)

    return _parse


def for_match(request_type=None):
    """
    :param request_type:

    :return:
    """

    def _parse(raw):
        result = g.parseString(raw, parseAll=True)
        return result.match

    request_type = request_type or Request
    g = match.grammar_for(*request_type.fields)('match')

    return _parse


def for_upstream():
    """
    :return:
    """

    def _parse(raw):
        result = g.parseString(raw, parseAll=True)
        return Upstream(*result.upstream.asList())

    g = upstream.grammar('upstream')

    return _parse
