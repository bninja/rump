"""
PyParsing grammar for matching expression DSL.
"""
import inspect
import logging
import re

try:
    from collections import OrderedDict
except ImportError:
    from ordereddict import OrderedDict

from pyparsing import *

from .. import types, and_, or_


logger = logging.getLogger(__name__)


def grammar_for(*fields):
    return operatorPrecedence(
        field_exprs(*fields),
        opList=[
            (not_op, 1, opAssoc.RIGHT, lambda ts: [~ts[0][1]]),
            (and_op, 2, opAssoc.LEFT, lambda ts: and_(*ts[0][0::2])),
            (or_op, 2, opAssoc.LEFT, lambda ts: or_(*ts[0][0::2])),
        ],
        lpar=lpar,
        rpar=rpar,
    )

# constants

null_l = Literal('null').setParseAction(lambda ts: [None])

# markers

lpar = Literal('(').suppress()
rpar = Literal(')').suppress()
lbrac = Literal('[').suppress()
rbrac = Literal(']').suppress()
markers = '()[]!'


# type operators

inv = Optional(
    Literal('!') | (Literal('not') + White(min=1).suppress()),
    default=False
).setParseAction(lambda ts: [ts[0] is not False])('inv')

sw = Group(
    inv +
    Literal('startswith').setParseAction(lambda ts: ['startswith'])('name')
)

ew = Group(
    inv +
    Literal('endswith').setParseAction(lambda ts: ['endswith'])('name')
)

in_ = Group(
    inv +
    Literal('in').setParseAction(lambda ts: ['in'])('name')
).leaveWhitespace()

eq = Group(
    inv +
    Literal('=').setParseAction(lambda ts: ['equal'])('name')
).leaveWhitespace()

pat = Group(
    inv +
    Literal('~').setParseAction(lambda ts: ['match'])('name') +
    Optional(Literal('*'), default=False).setParseAction(lambda ts: [ts[0] is not False])('ci')
)

lt = Literal('<').setParseAction(lambda ts: ['less'])('name')

lte = Literal('<=').setParseAction(lambda ts: ['less_equal'])('name')

gt = Literal('>').setParseAction(lambda ts: ['greater'])('name')

gte = Literal('>=').setParseAction(lambda ts: ['greater_equal'])('name')

# combine operators

not_op = Literal('!') | (Literal('not') + White(min=1).suppress())
and_op = Literal('and') | Literal('&&')
or_op = Literal('or') | Literal('||')


# boolean type

true_l = Literal('true').setParseAction(lambda ts: True)
false_l = Literal('false').setParseAction(lambda ts: False)
bool_l = true_l | false_l


def bool_expr(keywords):
    return (
        (keywords('field') +
         White(min=1).suppress() +
         eq('op') + (null_l ^ bool_l)('value')).setParseAction(as_field_expr) |
        keywords('field')
    )

# ipv4  type

ip4_l = Regex(
    r'((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)'
).setParseAction(lambda ts: [types.IPAddress(ts[0])])

ip4_cidr_l = Regex(
    r'((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)/(3[0-2]|[1-2]?[0-9])'
).setParseAction(lambda ts: [types.IPNetwork(ts[0])])


def ip4_expr(keywords):
    return (
        keywords('field') + White(min=1).suppress() + (
        (eq('op') + (null_l ^ ip4_l)('value')) |
        (in_('op') + ip4_cidr_l('value'))
    )).setParseAction(as_field_expr)

# number type

int_l = Regex(r'(\+|\-)?\d+').setParseAction(lambda ts: int(ts[0]))
int_list_l = lbrac + delimitedList(int_l, delim=',') + rbrac


def int_expr(keywords):
    return (
        keywords('field') + White(min=1).suppress() + (
            (eq('op') + (null_l ^ int_l)('value')) ^
            ((lte ^ lt ^ gte ^ gt)('op') + int_l('value')) ^
            (in_('op') + int_list_l('value'))
        )
    ).setParseAction(as_field_expr)

# string type

str_chars = printables
str_unquoted_chars = alphanums

str_l = (
    QuotedString('"', escChar='\\') |
    QuotedString("'", escChar='\\') |
    Word(str_unquoted_chars)
)
str_list_l = lbrac + delimitedList(str_l, delim=',') + rbrac


def as_regex(string, loc, tokens):
    token = tokens[0]
    if len(token) >= 2:
        if token[0] == token[1] == '"':
            token = token[1:-1]
        elif token[0] == token[1] == "'":
            token = token[1:-1]
    try:
        re.compile(token)
    except re.error as ex:
        raise ParseException(
            token, loc, '{0} not in a valid regular expression - {1}'.format(token, ex)
        )
    return [token]

str_pat_l = str_l.copy().setParseAction(as_regex)


def str_expr(keywords):
    return (
        (keywords('field') + White(min=1).suppress() + (
            (pat('op') + str_pat_l('value')) ^
            (eq('op') + (null_l ^ str_l)('value')) ^
            ((sw ^ ew)('op') + str_l('value')) ^
            (in_('op') + str_list_l('value')))) |
        (str_l('value') + White(min=1).suppress() + in_('op') + keywords('field'))
    ).setParseAction(as_field_expr)


# header type

header_name_chars = printables.translate(None, markers + ' <>@,;:\"/?={}')
header_name_l = Word(header_name_chars, min=1)


def header_expr(keywords):
    header_item = (
        keywords + Suppress('.') + header_name_l
    ).leaveWhitespace().setParseAction(as_subfield)('field')
    return (
        (header_item + White(min=1).suppress() + pat('op') + str_pat_l('value')) |
        (header_item + White(min=1).suppress() + (eq ^ sw ^ ew)('op') + str_l('value')) |
        (header_item + White(min=1).suppress() + in_('op') + str_list_l('value')) |
        (header_name_l('value') + White(min=1).suppress() + in_('op') + keywords('field'))
    ).setParseAction(as_field_expr)


# argument type

arg_name_chars = printables.translate(None, markers + ' ')
arg_name_l = Word(arg_name_chars, min=1)

arg_value_chars = printables
arg_value_l = Word(arg_value_chars)


def arg_expr(keywords):
    arg_item = (
        keywords + Suppress('.') + arg_name_l
    ).leaveWhitespace().setParseAction(as_subfield)('field')
    return (
        (arg_item + White(min=1).suppress() + pat('op') + str_pat_l('value')) |
        (arg_item + White(min=1).suppress() + (eq ^ sw ^ ew)('op') + str_l('value')) |
        (arg_item + White(min=1).suppress() + in_('op') + str_list_l('value')) |
        (arg_name_l('value') + White(min=1).suppress() + (in_)('op') + keywords('field'))
    ).setParseAction(as_field_expr)


# fields

def as_field(field):

    def _as_field(ts):
        return [field]

    return _as_field


def as_subfield(ts):
    field, name = ts
    return [getattr(field, name)]


def as_field_equal(field, ts):
    return field == ts.value


def as_field_match(field, ts):
    return field.match(ts.value, ignore_case=ts.op.ci)


def as_field_startswith(field, ts):
    return field.startswith(ts.value)


def as_field_endswith(field, ts):
    return field.endswith(ts.value)


def as_field_in(field, ts):
    if isinstance(ts.value, basestring):
        return field.contains(ts.value)
    elif isinstance(ts.value, ParseResults):
        return field.in_(ts.value.asList())
    return field.in_(ts.value)


def as_field_less(field, ts):
    return field < ts.value


def as_field_less_equal(field, ts):
    return field <= ts.value


def as_field_greater(field, ts):
    return field > ts.value


def as_field_greater_equal(field, ts):
    return field >= ts.value


as_field_mapping = {
    'equal': as_field_equal,
    'match': as_field_match,
    'startswith': as_field_startswith,
    'endswith': as_field_endswith,
    'in': as_field_in,
    'less': as_field_less,
    'less_equal': as_field_less_equal,
    'greater': as_field_greater,
    'greater_equal': as_field_greater_equal,
}


def as_field_expr(ts):
    try:
        field = ts.field
        if isinstance(field, (list, ParseResults)):
            field = field[0]
        if isinstance(ts.op, basestring):
            e = as_field_mapping[ts.op](field, ts)
        else:
            op = ts.op
            e = as_field_mapping[op.name](field, ts)
            if op.inv:
                e = ~e
        return [e]
    except Exception, ex:
        logger.exception(ex)
        raise


def field_exprs(*fields):

    def _match(candidate, target):
        if candidate is target:
            return True
        if not inspect.isclass(candidate):
            return False
        for base_type in inspect.getmro(candidate):
            if base_type is target:
                return True
        return False

    def _select(candidate):
        for target, bucket in keywords.iteritems():
            if _match(candidate, target):
                return bucket

    keywords = OrderedDict([
        (types.bool, ([], bool_expr)),
        (types.str, ([], str_expr)),
        (types.int, ([], int_expr)),
        (types.IPAddress, ([], ip4_expr)),
        (types.HeaderHash, ([], header_expr)),
        (types.ArgumentHash, ([], arg_expr)),
        (types.StringHash, ([], arg_expr)),
    ])

    keyword_re = re.compile('[a-zA-Z][_a-zA-Z0-9]*')

    fields = list(fields)

    while fields:
        field = fields.pop()
        if not keyword_re.match(field.name):
            raise ValueError(
                'Field {field} name {name} is invalid, must match {pattern}.'.format(
                field=field, name=field.name, pattern=keyword_re.pattern
            ))
        if issubclass(field.type, types.NamedTuple):
            if field.type.fields:
                fields.extend([
                    getattr(field, subfield.name)
                    for subfield in field.type.fields
                ])
            continue
        hit = _select(field.type)
        if hit is None:
            logger.warning(
                'field "%s" type %s is not supported, must be one of %s',
                field.path, field.type, keywords.keys()
            )
            continue
        keyword = (
            Keyword(field.path)(field.path).setParseAction(as_field(field))
        )
        hit[0].append(keyword)

    return Or(exprs=[
        expr(Or(exprs=bucket))
        for bucket, expr in keywords.itervalues() if bucket
    ])
