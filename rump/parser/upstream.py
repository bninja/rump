"""
"""
from pyparsing import *

from ..upstream import Server, Selection, Upstream


def as_server(ts):
    t = ts[0]
    if len(t) > 1:
        v = tuple(t)
    else:
        v = Server.default_protcol, t[0]
    return [Server(*v)]


proto_l = Literal('http') ^ Literal('https')
host_chars = printables.translate(None, ', ')
sever = Group(
    Optional(proto_l + Suppress('://')) +
    Word(host_chars, min=1)
).leaveWhitespace().setParseAction(as_server)


def as_selection(ts):
    t = ts[0]
    if len(t) > 1:
        v = tuple(t)
    else:
        v = t[0], 1
    return [Selection(*v)]

weight = Word(nums).setParseAction(lambda ts: int(ts[0]))
selection = Group(
    sever + Optional(Suppress(',') + weight)
).setParseAction(as_selection)


def as_upstream(ts):
    return [Upstream(ts[0].asList())]


grammar = Group(
    delimitedList(selection, delim=White(' ', min=1))
).leaveWhitespace().setParseAction(as_upstream)
