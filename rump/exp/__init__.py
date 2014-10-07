"""
Expression language for representing matches. Other than these helpers:

- or_
- and_
- not_

you usually never need to access anything in here directly but instead via
``rump.Request`` fields, e.g.:

.. code:: python

    assert isinstance(
        rump.Request.path.startwith('/v1/'),
        rump.exp.FieldStartswith
    )

"""
import collections
import copy
import re

from . import types

__all__ = [
    'types',
    'Symbols',
    'Expression',
    'UnaryOp',
    'BoolOp',
    'Or',
    'or_',
    'And'
    'and_',
    'Not',
    'not_',
    'FieldOp',
    'FieldIn',
    'FieldLessThan',
    'FieldLessThanEqual',
    'FieldEqual',
    'FieldGreaterThan',
    'FieldGreaterThanEqual',
    'FieldContains',
    'FieldStartswith',
    'FieldEndswith',
    'FieldMatch',
]


class Context(dict):
    """
    Context used when evaluating a **compiled** expression.
    """

    class Cache(collections.defaultdict):

        def __init__(self, request):
            self.request = request
            super(Context.Cache, self).__init__()

        def __missing__(self, field):
            v = field.__get__(self.request)
            self[field] = v
            return v

    def __init__(self, request, symbols):
        kwargs = {
            'request': self.Cache(request),
        }
        kwargs.update(symbols)
        super(Context, self).__init__(kwargs)


class Symbols(dict):
    """
    Collection of symbols used when evaluating a **compiled** expression.
    """

    def field(self, f):
        key = 'field_' + str(id(f))
        if key not in self:
            self[key] = f
        return key

    def literal(self, l):
        key = 'literal_' + str(id(l))
        if key not in self:
            self[key] = l
        return key


class Expression(object):
    """
    Base expression.
    """

    def __and__(self, other):
        return And(self, other)

    def __or__(self, other):
        return Or(self, other)

    def __call__(self, request):
        raise NotImplementedError

    @property
    def children(self):
        return None

    PREFIX = 'PREFIX'

    INFIX = 'INFIX'

    POSTFIX = 'POSTFIX'

    def traverse(self, bool_op=None, field_op=None, order=PREFIX):
        """
        Traverses this expression tree.

        :param bool_op: Called when visiting an `rump.fields.BoolOp`.
        :param field_op: Called when visiting an `rump.fields.FieldOp`.
        :param order: Traversal ordering, defaults to `rump.Expression.PREFIX`.
        """
        visit = lambda x: x
        if isinstance(self, BoolOp):
            visit = bool_op or visit
        elif isinstance(self, (FieldOp, UnaryOp)):
            visit = field_op or visit
        else:
            raise Exception('Unable to visit {0} type'.format(type(self)))
        if self.children:
            l, r = self.children
            if order is self.PREFIX:
                visit(self)
                l.traverse(bool_op, field_op, order)
                r.traverse(bool_op, field_op, order)
            elif order is self.INFIX:
                l.traverse(bool_op, field_op, order)
                visit(self)
                r.traverse(bool_op, field_op, order)
            elif order is self.POSTFIX:
                l.traverse(bool_op, field_op, order)
                r.traverse(bool_op, field_op, order)
                visit(self)
            else:
                raise ValueError('Invalid traversal order "{0}"'.format(order))
        else:
            visit(self)

    @classmethod
    def _field_literal(cls, f):
        if isinstance(f, SubField):
            return '{0}.{1}'.format(cls._field_literal(f.field), f.name)
        return f.name

    @classmethod
    def _str_literal(cls, l):
        if l is None:
            return 'null'
        if isinstance(l, basestring):
            return '"{0}"'.format(l.replace('"', '\\"'))
        if isinstance(l, int):
            return str(l)
        if isinstance(l, types.IPAddress):
            return str(l)
        if isinstance(l, types.IPNetwork):
            return str(l)
        if isinstance(l, (list, tuple)):
            return '[{0}]'.format(
                ', '.join([cls._str_literal(v) for v in l])
            )
        raise ValueError('Unable to convert {0} to literal'.format(literal=l))

    def __str__(self):
        raise NotImplementedError

    symbols = Symbols

    def compile(self, symbols):
        raise NotImplementedError

    def __eq__(self, other):
        return str(self) == str(other)

    def __ne__(self, other):
        return ~self.__eq__(other)


class UnaryOp(object):

    pass


class BoolOp(Expression):

    name = None

    precedence = 0

    def __init__(self, lhs, rhs):
        self.lhs = lhs
        self.rhs = rhs

    @property
    def children(self):
        return self.lhs, self.rhs

    def __str__(self):
        l = str(self.lhs)
        if (isinstance(self.lhs, BoolOp) and
            self.lhs.precedence < self.precedence):
            l = '({0})'.format(l)
        r = '{0}'.format(self.rhs)
        return ' '.join([l, self.name, r])

    def compile(self, symbols):
        l = self.lhs.compile(symbols)
        if (isinstance(self.lhs, BoolOp) and
            self.lhs.precedence < self.precedence):
            l = '({0})'.format(l)
        r = self.rhs.compile(symbols)
        return ' '.join([l, self.name, r])


def not_(expr):
    return ~expr


class And(BoolOp):

    def __invert__(self):
        return Or(~self.lhs, ~self.rhs)

    def __call__(self, request):
        return self.lhs(request) and self.rhs(request)

    name = 'and'

    precedence = 10


def and_(lhs, rhs, *exprs):
    op = And(lhs, rhs)
    return reduce(And, exprs, op)


class Or(BoolOp):

    def __invert__(self):
        return And(~self.lhs, ~self.rhs)

    def __call__(self, request):
        return self.lhs(request) or self.rhs(request)

    name = 'or'

    precedence = 5


def or_(lhs, rhs, *exprs):
    op = Or(lhs, rhs)
    return reduce(Or, exprs, op)


class SubField(object):

    type = None

    def __init__(self, field, name):
        self.field = field
        self.name = name

    @property
    def path(self):
        return '{field}.{name}'.format(field=self.field.path, name=self.name)

    def __get__(self, request):
        if request is None:
            return self
        v = self.field.__get__(request)
        if v is None:
            return v
        return getattr(v, self.name, None)


class FieldOp(Expression):

    name = None

    default = False

    inv = False

    def __init__(self, field, literal):
        self.field = field
        self.literal = literal
        self.inv = False

    def _evaluate_for(self, value):
        raise NotImplementedError()

    # Expression

    def __invert__(self):
        other = copy.copy(self)
        other.inv = not other.inv
        return other

    def __call__(self, request):
        field_value = self.field.__get__(request)
        result = self._evaluate_for(field_value)
        if self.inv:
            result = not result
        return result

    def __str__(self):
        return '{inv}{field} {op} {literal}'.format(
            inv='not ' if self.inv else '',
            field=self._field_literal(self.field),
            op=self.name,
            literal=self._str_literal(self.literal),
        )

    def compile(self, symbols):
        field_key = symbols.field(self.field)
        literal_key = symbols.literal(self.literal)
        return '{inv}request[{field}] {op} {literal}'.format(
            inv='not ' if self.inv else '',
            field=field_key,
            op=self.name,
            literal=literal_key,
        )


class FieldEqual(FieldOp):

    # Expression

    def __invert__(self):
        return FieldNotEqual(self.field, self.literal)

    def __str__(self):
        return '{field} = {literal}'.format(
            field=self._field_literal(self.field),
            literal=self._str_literal(self.literal),
        )

    def compile(self, symbols):
        field_key = symbols.field(self.field)
        if self.literal is None:
            return 'request[{field}] {inv}{op} None'.format(
                field=field_key,
                op='is',
                inv='not ' if self.inv else '',
            )
        else:
            literal_key = symbols.literal(self.literal)
            return '{inv}request[{field}] {op} {literal}'.format(
                inv='not ' if self.inv else '',
                field=field_key,
                op='==',
                literal=literal_key,
            )

    # FieldOp

    name = '='

    def _evaluate_for(self, value):
        if value is None:
            return self.literal is None
        return value == self.literal


class FieldNotEqual(FieldOp):

    # Expression

    def __invert__(self):
        return FieldEqual(self.field, self.literal)

    def __str__(self):
        return '{field} != {literal}'.format(
            field=self._field_literal(self.field),
            literal=self._str_literal(self.literal),
        )

    def compile(self, symbols):
        field_key = symbols.field(self.field)
        if self.literal is None:
            return 'request[{field}] is not None'.format(
                field=field_key,
            )
        else:
            literal_key = symbols.literal(self.literal)
            return 'request[{field}] != {literal}'.format(
                field=field_key,
                literal=literal_key,
            )

    # FieldOp

    name = '!='

    default = True

    def _evaluate_for(self, value):
        if value is None:
            return self.literal is not None
        return value != self.literal


class FieldLessThan(FieldOp):

    # FieldOp

    name = '<'

    default = False

    def _evaluate_for(self, value):
        if value is None:
            return self.default
        return value < self.literal


class FieldLessThanEqual(FieldOp):

    # FieldOp

    name = '<='

    default = False

    def _evaluate_for(self, value):
        if value is None:
            return self.default
        return value <= self.literal


class FieldGreaterThan(FieldOp):

    # FieldOp

    name = '>'

    default = False

    def _evaluate_for(self, value):
        if value is None:
            return self.default
        return value > self.literal


class FieldGreaterThanEqual(FieldOp):

    # FieldOp

    name = '>='

    default = False

    def _evaluate_for(self, value):
        if value is None:
            return self.default
        return value >= self.literal


class FieldStartswith(FieldOp):

    # Expression

    def compile(self, symbols):
        field_key = symbols.field(self.field)
        literal_key = symbols.literal(self.literal)
        return '{inv}(request[{field}] and request[{field}].{name}({literal}))'.format(
            inv='not ' if self.inv else '',
            field=field_key,
            name=self.name,
            literal=literal_key,
        )

    # FieldOp

    name = 'startswith'

    def _evaluate_for(self, value):
        if value is None:
            return self.default
        return value is not None and value.startswith(self.literal)


class FieldEndswith(FieldOp):

    # Expression

    def compile(self, symbols):
        field_key = symbols.field(self.field)
        literal_key = symbols.literal(self.literal)
        return '{inv}(request[{field}] and request[{field}].{name}({literal}))'.format(
            inv='not ' if self.inv else '',
            field=field_key,
            name=self.name,
            literal=literal_key,
        )

    # FieldOp

    name = 'endswith'

    def _evaluate_for(self, value):
        if value is None:
            return self.default
        return value is not None and value.endswith(self.literal)


class FieldMatch(FieldOp):

    # Expression

    def __str__(self):
        return '{field} {inv}{op}{ci} "{pattern}"'.format(
            field=self._field_literal(self.field),
            inv='!' if self.inv else '',
            op=self.name,
            ci='*' if (self.literal.flags & re.I) else '',
            pattern=self.literal.pattern
        )

    def compile(self, symbols):
        field_key = symbols.field(self.field)
        literal_key = symbols.literal(self.literal)
        return '{inv}(request[{field}] is not None and request[{field}].match({literal}))'.format(
            inv='not ' if self.inv else '',
            field=field_key,
            literal=literal_key,
        )

    # FieldOp

    name = '~'

    def _evaluate_for(self, value):
        if value is None:
            return self.default
        return self.literal.match(value) is not None


class FieldIn(FieldOp):

    # Expression

    def __str__(self):
        return '{field} {inv}{op} {literal}'.format(
            field=self._field_literal(self.field),
            inv='not ' if self.inv else '',
            op=self.name,
            literal=self._str_literal(self.literal),
        )

    def compile(self, symbols):
        field_key = symbols.field(self.field)
        literal_key = symbols.literal(self.literal)
        return '{inv}request[{field}] {op} {literal}'.format(
            inv='not ' if self.inv else '',
            field=field_key,
            op=self.name,
            literal=literal_key,
        )

    # FieldOp

    name = 'in'

    def _evaluate_for(self, value):
        if value is None:
            return self.default
        return value in self.literal


class FieldContains(FieldOp):

    # Expression

    def __str__(self):
        return '{literal} {inv}{op} {field}'.format(
            literal=self.literal,
            inv='not ' if self.inv else '',
            op=self.name,
            field=self._field_literal(self.field),
        )

    def compile(self, symbols):
        field_key = symbols.field(self.field)
        literal_key = symbols.literal(self.literal)
        return '{literal} {inv}{op} request[{field}]'.format(
            literal=literal_key,
            inv='not ' if self.inv else '',
            op=self.name,
            field=field_key,
        )

    # FieldOp

    name = 'in'

    def _evaluate_for(self, value):
        if value is None:
            return self.default
        return self.literal in value
