from pyparsing import *

from . import upstream
from . import match


def grammar_for(fields, upstream_aliases=None):
    upstream_aliases = [
        Keyword(alias).setParseAction(lambda x: upstream_aliases[x[0]])
        for alias in (upstream_aliases or {}).iterkeys()
    ]

    p = (
        match.grammar_for(*fields)('match') +
        White().suppress() + Suppress('=>') + White().suppress() +
        Or(exprs=[upstream.grammar] + upstream_aliases)('upstream')
    )

    return p
