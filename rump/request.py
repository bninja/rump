import base64
import copy
import inspect
import logging
import re
import urlparse

import pilo

from . import Expression, exp, types

logger = logging.getLogger(__name__)

__all__ = [
    'PathMixin',
    'String',
    'Boolean',
    'Integer',
    'IPAddress',
    'IPNetwork',
    'NamedTuple'
    'StringHash',
    'ArgumentHash',
    'HeaderHash',
]


class PathMixin(object):
    """
    Mix-in for adding `.path` property to a field.
    """

    @property
    def path(self):
        return self.name


class BooleanMixin(Expression):
    """
    Mix-in for adding boolean expression capabilities to a field with type
    ``rump.type.bool``.
    """

    inv = False

    def __eq__(self, other):
        return exp.FieldEqual(self, other)

    def __ne__(self, other):
        return exp.FieldNotEqual(self, other)

    def __invert__(self):
        other = copy.copy(self)
        other.inv = not other.inv
        return other

    # Expression

    def __call__(self, request):
        value = self.__get__(request)
        result = False if value is None else value
        if self.inv:
            result = not result
        return result

    def __str__(self):
        return '{inv}{op}'.format(
            inv='not ' if self.inv else '',
            op=self.name,
        )

    def compile(self, symbols):
        field_key = symbols.field(self)
        return '{inv}request[{field}]'.format(
            inv='not ' if self.inv else '',
            field=field_key,
        )


class Boolean(BooleanMixin, pilo.fields.Boolean, exp.UnaryOp, PathMixin):

    type = bool


class BooleanSubField(BooleanMixin, exp.SubField):

    type = bool


class StringMixin(object):
    """
    Mix-in for adding string expression capabilities to a field with type
    ``rump.type.str``.
    """

    def __eq__(self, other):
        return exp.FieldEqual(self, other)

    def __ne__(self, other):
        return exp.FieldNotEqual(self, other)

    def contains(self, item):
        return exp.FieldContains(self, item)

    def in_(self, others):
        return exp.FieldIn(self, others)

    def match(self, pattern, ignore_case=False):
        flags = 0
        if ignore_case:
            flags |= re.I
        pattern_re = re.compile(pattern, flags)
        return exp.FieldMatch(self, pattern_re)

    def startswith(self, prefix):
        return exp.FieldStartswith(self, prefix)

    def endswith(self, suffix):
        return exp.FieldEndswith(self, suffix)


class String(pilo.fields.String, PathMixin, StringMixin):

    type = str


class StringSubField(exp.SubField, StringMixin):

    type = str


class IntegerMixin(object):
    """
    Mix-in for adding integer expression capabilities to a field with type
    ``rump.type.int``.
    """

    def __eq__(self, other):
        return exp.FieldEqual(self, other)

    def __ne__(self, other):
        return exp.FieldNotEqual(self, other)

    def __lt__(self, other):
        return exp.FieldLessThan(self, other)

    def __le__(self, other):
        return exp.FieldLessThanEqual(self, other)

    def __gt__(self, other):
        return exp.FieldGreaterThan(self, other)

    def __ge__(self, other):
        return exp.FieldGreaterThanEqual(self, other)

    def in_(self, others):
        return exp.FieldIn(self, others)


class Integer(pilo.fields.Integer, PathMixin, IntegerMixin):

    type = int


class NamedTuple(pilo.Field, PathMixin):

    type = pilo.NOT_SET

    def __init__(self, *args, **kwargs):
        self.type = kwargs.pop('type', pilo.NOT_SET)
        if self.type is pilo.NOT_SET:
            args, self.type = pilo.fields.pluck(args, lambda arg: (
                inspect.isclass(arg) and issubclass(arg, types.NamedTuple)
            ))
            if self.type is pilo.NOT_SET:
                raise TypeError('Missing type=NamedTuple')
        super(NamedTuple, self).__init__(*args, **kwargs)

    def __getattr__(self, name):
        field = getattr(self.type, name, None)
        if field is None:
            raise AttributeError(
                '{0}.{1} does not exist'.format(self.type, name)
            )
        if not hasattr(field, 'type'):
            raise AttributeError(
                '{0}.{1}.type does not exist'.format(self.type, name)
            )
        if issubclass(field.type, str):
            sub_field_type = StringSubField
        elif issubclass(field.type, bool):
            sub_field_type = BooleanSubField
        else:
            raise TypeError(
                '{0}.{1}.type={2} is not supported, must be on of {3}'
                .format(self.type, name, field.type, [str, bool])
            )
        sub_field = sub_field_type(self, name)
        setattr(self, name, sub_field)
        return sub_field


class StringHash(pilo.Field, PathMixin):

    type = types.StringHash

    def __getattr__(self, name):
        return StringSubField(self, name)

    def contains(self, item):
        return exp.FieldContains(self, item)


class ArgumentHash(pilo.Field, PathMixin):

    type = types.ArgumentHash

    def __getattr__(self, name):
        return StringSubField(self, name)

    def contains(self, item):
        return exp.FieldContains(self, item)


class IPAddress(pilo.Field, PathMixin):

    type = types.IPAddress

    def __eq__(self, other):
        return exp.FieldEqual(self, other)

    def __ne__(self, other):
        return exp.FieldNotEqual(self, other)

    def in_(self, others):
        return exp.FieldIn(self, others)


class Object(pilo.Field, PathMixin):

    type = object


class HeaderHash(pilo.fields.Group, PathMixin):

    type = types.HeaderHash

    def __init__(self, *args, **kwargs):
        super(HeaderHash, self).__init__(
            (re.compile('HTTP\_(.+)'), String()), *args, **kwargs
        )

    def _munge(self, value):
        return dict(
            (match.group(0).lower(), value)
            for _, match, value in super(HeaderHash, self)._munge(value)
        )

    def __getattr__(self, name):
        return StringSubField(self, name)

    def contains(self, item):
        return exp.FieldContains(self, item)


class BasicAuthorization(types.NamedTuple):

    username = String()

    password = String()


class Request(pilo.Form):
    """
    Defines a request schema as collections of fields:

    - ``rump.request.String``
    - ``rump.request.Integer`
    - ``rump.request.NamedTuple``
    - ...

    all of which parse or compute values that one of these ``rump.types``. If
    you need to add custom fields just:

    .. code:: python

        import rump

        class MyRequest(rump.Request)

            x_sauce = rump.request.String('HTTP_X_SAUCE', default='blue')

            env = rump.request.String()

            @env.compute
            def env(self)
                if not self.authorized or not self.password:
                    return 'public'
                return self.password.split('-')[0]

    which can then be used in matching expressions:

    .. code:: python

        print rump._and(MyRequest.x_sauce.in_(['mayo', 'ketchup']), MyRequest.env != 'open')

    """

    def __init__(self, environ, router=None):
        """
        :param environ: The WSGI environment for the request. This will be
                        wrapped and stored as `src`.
        :param router: Optional `Router` examining this request. This can be
                       useful when fields uses `Router` information when
                       computing a value.
        """
        super(Request, self).__init__()
        self.src = pilo.source.DefaultSource(environ)
        self.router = router

    def context(self, symbols):
        """
        Creates a context for this request to be used when evaluating a
        **compiled** rule.

        :param symbols: An instance of `exp.Symbols`.

        :return: The `exp.Context` for this request.
        """
        return exp.Context(self, symbols)

    method = String('REQUEST_METHOD')

    path = String('PATH_INFO')

    query_string = String('QUERY_STRING')

    query = ArgumentHash()

    @query.compute
    def query(self):
        if self.query_string:
            query = dict(
                (k, v[-1])
                for k, v in urlparse.parse_qs(self.query_string).iteritems()
            )
        else:
            query = {}
        query_hash = types.StringHash(**query)
        return query_hash

    content_type = String('CONTENT_TYPE', default=None)

    content_length = Integer('CONTENT_LENGTH', default=None)

    headers = HeaderHash()

    host = String('HTTP_HOST')

    authenticated = Boolean('HTTP_AUTHORIZATION', default=False)

    @authenticated.parse
    def authenticated(self, path):
        return path.exists and not path.is_null

    basic_authorization = NamedTuple(
        BasicAuthorization, 'HTTP_AUTHORIZATION', default=None
    )

    @basic_authorization.parse
    def basic_authorization(self, path):
        v = path.primitive(basestring)
        if not v.startswith('Basic '):
            return
        encoded = v[len('Basic '):]
        try:
            username, _, password = base64.b64decode(encoded).partition(':')
        except (TypeError, ValueError):
            return
        return BasicAuthorization(username=username, password=password)

    username = String(nullable=True)

    @username.compute
    def username(self):
        if self.basic_authorization:
            return self.basic_authorization.username

    password = String(nullable=True)

    @password.compute
    def password(self):
        if self.basic_authorization:
            return self.basic_authorization.password

    client_ip4 = IPAddress('REMOTE_ADDR')

    @client_ip4.parse
    def client_ip4(self, path):
        return types.IPAddress(path.primitive(basestring))

    has_content = Boolean()

    @has_content.compute
    def has_content(self):
        return (
            self.content_type is not None and
            self.content_length not in((0, None))
        )

    content = String('wsgi.input')

    @content.parse
    def content(self, path):
        if not self.has_content:
            return None
        io = path.value
        if not io:
            return b''
        return io.read(self.content_length)
