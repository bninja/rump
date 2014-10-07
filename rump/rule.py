import collections
import logging
import StringIO

from . import exc, Request, Expression


logger = logging.getLogger(__name__)


class CompiledRule(object):
    """
    Compiled version of a routing rule.

    `symbols`
        A `rump.fields.Symbols` table used to store symbolic information used
        in the compiled rule.

    `expression`
        The `rump.fields.Expression` which has been compiled.

    `compiled`
        Byte code for evaluating a `rump.fields.Expression`.

    `upstream`
        The `rump.Upstream` to be returned on a match.

    You don't usually need to create these directly. Instead grab them from
    the source `rump.Rule` like:

        my_compiled_rule = rump.parser.for_rule()("my-rule-string").compile()

    """

    def __init__(self, expression, upstream, symbols=None):
        self.expression = expression
        self.upstream = upstream
        self.symbols = (
            self.expression.symbols() if symbols is None else symbols
        )
        self.compiled = compile(
            expression.compile(self.symbols), '<string>', 'eval'
        )

    def match_context(self, request_context):
        """
        Determines whether a request represented by a context matches this rule.

        :param context: A `rump.RequestContext`.

        :return rump.Upstream:
            If the request matches this rule then the associated upstream is
            returned, otherwise None.
        """
        matched = eval(self.compiled, None, request_context)
        return self.upstream if matched else None

    def match(self, request):
        """
        Determines whether a request matches this rule.

        :param request: A `rump.Request`.

        :return rump.Upstream:
            If the request matches this rule then the associated upstream is
            returned, otherwise None.
        """
        matched = self.match_context(request.context(self.symbols))
        return self.upstream if matched else None

    def __str__(self):
        return '{} => {}'.format(str(self.expression), str(self.upstream))

    def __eq__(self, other):
        return (
            isinstance(other, (Rule, CompiledRule)) and
            self.expression == other.expression and
            self.upstream == other.upstream
        )

    def __ne__(self, other):
        return not self.__eq__(other)


class Rule(object):
    """
    Represents a "routing" rule used to match requests to an upstream.

    `expression`
        A `rump.fields.Expression`.

    `upstream`
        The `rump.Upstream` to be returned on a match.

    There are two ways to express a Rule:

    - A `rump.fields.Expression`.
    - String, see `rump.rule.grammar` for the grammar.

    If you have a string just do something like:

        rule = rump.parser.for_rule()("my-rule-string")

    """

    compiled_type = CompiledRule

    def __init__(self, expression, upstream):
        self.expression = expression
        self.upstream = upstream

    def match(self, request):
        """
        Determines whether a request matches this rule.

        :param request: The rump.Request to evaluate for a match.
        :param cache: Optional map used to cache request field lookups.

        :return rump.Upstream:
            If the request matches this rule then the associated upstream is
            returned, otherwise None.
        """
        matched = self.expression(request)
        return self.upstream if matched else None

    def compile(self, symbols=None):
        """
        Compiles this rule.

        :param symbols:
            A `rump.fields.Symbols` table used to store symbolic information
            used in the compiled rule.

        :return CompiledRule: The equivalent compiled rule.
        """
        return CompiledRule(self.expression, self.upstream, symbols)

    def __str__(self):
        return '{0} => {1}'.format(self.expression, self.upstream)

    def __eq__(self, other):
        return (
            isinstance(other, (Rule, CompiledRule)) and
            self.expression == other.expression and
            self.upstream == other.upstream
        )

    def __ne__(self, other):
        return not self.__eq__(other)


class Rules(collections.MutableSequence):
    """
    A collection of "routing" rules used to match requests to an upstream.

    `request_type`
        Specification of the requests these rules will be matching. Defaults
        to `rump.Request`.

    `compile`
        Flag determining whether added rules are compiled.

    `strict`
        Flag determining whether added rules are compiled.

    `auto_disable`
        Flag determining whether to auto disable a rule that generates and
        error when attempting to match a request.
    """

    def __init__(self, *rules, **options):
        self._parse_rule = None
        self.symbols = None
        self._compile = False
        self.disabled = set()

        self._rules = []
        if len(rules) == 1 and isinstance(rules[0], list):
            rules = rules[0]
        for rule in rules:
            self._rules.append(rule)

        # options
        self.request_type = options.pop('request_type', Request)
        self.compile = options.pop('compile', False)
        self.strict = options.pop('strict', True)
        self.auto_disable = options.pop('auto_disable', False)
        if options:
            raise TypeError(
                'Unexpected keyword argument {0}'.format(options.keys()[0])
            )

    @property
    def compile(self):
        return self._compile

    @compile.setter
    def compile(self, value):
        if value == self._compile:
            return
        self._compile = value
        if self._compile:
            self.symbols = Expression.symbols()
            for i in xrange(len(self)):
                self[i] = Rule(
                    self[i].expression, self[i].upstream
                ).compile(self.symbols)
        else:
            self.symbols = None
            for i in xrange(len(self)):
                self[i] = Rule(self[i].expression, self[i].upstream)

    @property
    def parse_rule(self):
        from . import parser

        if not self._parse_rule:
            self._parse_rule = parser.for_rule(self.request_type)
        return self._parse_rule

    def load(self, io, strict=None):
        strict = self.strict if strict is None else strict
        for i, line in enumerate(io):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            try:
                rule = self.parse_rule(line)
            except exc.ParseException, ex:
                if strict:
                    raise
                logger.warning(
                    '%s, line %s, unable to parse rule - %s, skipping',
                    getattr(io, 'name', '<memory>'), i, ex,
                )
                continue
            self.append(rule)
        return self

    def loads(self, s, strict=None):
        io = StringIO.StringIO(s)
        return self.load(io, strict=strict)

    def dump(self, io):
        for rule in self:
            io.write(str(rule))
            io.write('\n')

    def dumps(self):
        io = StringIO.StringIO()
        self.dump(io)
        return io.getvalue()

    def disable(self, i):
        self.disabled.add(self[i])

    def disable_all(self):
        self.disabled = set(self)

    def enable(self, i):
        self.disabled.remove(self[i])

    def enable_all(self):
        self.disabled.clear()

    def match(self, request, error=None):
        if error is None:
            error = 'suppress' if self.auto_disable is False else 'disable'
        if error not in ('raise', 'disable', 'suppress'):
            raise ValueError('error={0} invalid'.format(error))
        return (
            self._match_compiled if self.compile else self._match
        )(request, error)

    def _match_compiled(self, request, error):
        i, count, request_ctx = 0, len(self), request.context(self.symbols)
        while True:
            try:
                while i != count:
                    if self[i] not in self.disabled:
                        upstream = self[i].match_context(request_ctx)
                        if upstream:
                            return upstream
                    i += 1
                break
            except StandardError:
                raise
            except Exception as ex:
                if error == 'raise':
                    raise
                logger.exception('[%s] %s match failed - %s\n', i, self[i], ex)
                if error == 'disable':
                    self.disabled.add(self[i])
                i += 1

    def _match(self, request, error):
        i, count = 0, len(self)
        while True:
            try:
                while i != count:
                    if self[i] not in self.disabled:
                        upstream = self[i].match(request)
                        if upstream:
                            return upstream
                    i += 1
                break
            except StandardError:
                raise
            except Exception as ex:
                if error == 'raise':
                    raise
                logger.exception('[%s] %s match failed - %s\n', self[i], i, ex)
                if error == 'disable':
                    self.disabled.add(self[i])
                i += 1

    def __str__(self):
        return str(self._rules)

    def __eq__(self, other):
        return (
            (isinstance(other, Rules) and self._rules == other._rules) or
            (isinstance(other, list) and self._rules == other)
        )

    def __ne__(self, other):
        return not self.__eq__(other)

    # collections.MutableSequence

    def __getitem__(self, key):
        return self._rules[key]

    def __setitem__(self, key, value):
        if isinstance(value, basestring):
            rule = self.parse_rule(value)
        elif isinstance(value, Rule):
            rule = value
        elif isinstance(value, Rule.compiled_type):
            rule = Rule(value.expression, value.upstream)
        else:
            raise TypeError(
                '{0} is not a string, Rule or CompiledRule'.format(value)
            )
        if self.compile:
            rule = rule.compile(self.symbols)
        self._rules[key] = rule

    def __delitem__(self, key):
        self.disabled.difference_update(self.__getitem__(key))
        self._rules.__delitem__(key)

    def __len__(self):
        return len(self._rules)

    def insert(self, key, value):
        if isinstance(value, basestring):
            rule = self.parse_rule(value)
        elif isinstance(value, Rule):
            rule = value
        elif isinstance(value, Rule.compiled_type):
            rule = Rule(value.expression, value.upstream)
        else:
            raise ValueError(
                '{0} is not a string, Rule or CompiledRule'.format(value)
            )
        if self.compile:
            rule = rule.compile(self.symbols)
        self._rules.insert(key, rule)
