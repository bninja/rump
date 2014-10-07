"""
Parsers for:

- ``rump.Rule``
- ``rump.Expression`` and
- ``rump.Upstream``

DSLs.
"""
from .. import Rule, Request, Upstream
from . import match, upstream, rule


__all__ = [
    'for_rule',
    'for_match',
    'for_upsream',
]


def for_rule(request_type=None, upstream_aliases=None, rule_type=None):
    """
    Creates a parser for rule DSL strings.

    :param request_type: The request schema the parser should support. Defaults
                         to `rump.Request`.
    :param upstream_aliases: Optional mapping of names to a upstreams.
    :param rule_type: The rule type to create. Defaults `rump.Rule`.

    :return: Single argument callable for parsing a rule DSL string to
             `rule_type`.
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
    Creates a parser for expression DSL strings.

    :param request_type: The request schema the parser should support. Defaults
                         to `rump.Request`.

    :return: Single argument callable for parsing a matching expression DSL
             string to ``rump.exp.Expression``.
    """

    def _parse(raw):
        result = g.parseString(raw, parseAll=True)
        return result.match

    request_type = request_type or Request
    g = match.grammar_for(*request_type.fields)('match')

    return _parse


def for_upstream():
    """
    Creates a parser for upstream DSL strings.

    :return: Single argument callable for parsing an upstream DSL string to
             ``rump.Upstream``.
    """

    def _parse(raw):
        result = g.parseString(raw, parseAll=True)
        return Upstream(*result.upstream.asList())

    g = upstream.grammar('upstream')

    return _parse
