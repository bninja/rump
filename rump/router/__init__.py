"""
"""
import contextlib
import logging
import re

import pilo

from .. import exc, Request, parser, Rule, Rules, Upstream


logger = logging.getLogger(__name__)


class Dynamic(pilo.Form):
    """
    """

    _type_ = pilo.fields.Type.abstract()

    def can_connect(self, router):
        """
        :return:
        """
        raise NotImplementedError

    def connect(self, router):
        """
        :param router:
        """
        raise NotImplementedError

    def is_connected(self, router):
        """
        :param router:

        :return:
        """
        raise NotImplementedError

    def disconnect(self, router):
        """
        :param router:
        """
        raise NotImplementedError

    def load(self, router, cxn):
        """
        :param router:
        """
        raise NotImplementedError

    def save(self, router, cxn):
        """
        :param router:
        """
        raise NotImplementedError

    def watch(self, router, callback):
        """
        :param router:
        :param callback:
        """
        raise NotImplementedError


class Router(pilo.Form):
    """
    """

    #: Name of this router
    name = pilo.fields.String()

    #: Whether this router is enabled.
    enabled = pilo.fields.Boolean(default=True).tag('dynamic')

    #: Host patterns whose requests should be handle by this router.
    hosts = pilo.fields.List(pilo.fields.String(), default=list).tag('dynamic')

    @hosts.field.parse
    def hosts(self, path):
        value = path.primitive()
        if not isinstance(value, basestring):
            if not hasattr(value, 'match'):
                self.ctx.errors.invalid('not a string or regex')
                return pilo.ERROR
            return value
        try:
            return re.compile(value)
        except re.error, ex:
            self.ctx.errors.invalid('{0} - {1}'.format(str(ex), value))
            return pilo.ERROR

    #: Whether routing rules should be compiled.
    compile_rules = pilo.fields.Boolean(default=True).tag('dynamic')

    #: Whether to automatically disable failing rules.
    auto_disable_rules = pilo.fields.Boolean(default=True).tag('dynamic')

    #: Upstream to use when a request matches *no* routing rules.
    default_upstream = pilo.fields.String(default=None).tag('dynamic')

    @default_upstream.parse
    def default_upstream(self, path):
        value = path.primitive()
        if value is None:
            return value
        if isinstance(value, Upstream):
            return value
        try:
            return self.upstream_parser(value)
        except exc.ParseException, ex:
            self.ctx.errors.invalid(str(ex))
            return pilo.ERROR

    #: Type to use for representing requests.
    request_type = pilo.fields.Code(default=lambda: Request)

    #: Upstream selection rules.
    rules = pilo.fields.List(pilo.fields.String(), ignore=None)

    @rules.field.parse
    def rules(self, path):
        value = path.primitive()
        if isinstance(value, (Rule, Rule.compiled_type)):
            value = str(value)
        try:
            return self.rule_parser(value)
        except exc.ParseException, ex:
            self.ctx.errors.invalid(str(ex))
            return pilo.ERROR

    @rules.default
    def rules(self):
        return Rules(
            auto_disable=self.auto_disable_rules,
            compile=self.compile_rules,
        )

    @rules.munge
    def rules(self, value):
        return Rules(
            value,
            auto_disable=self.auto_disable_rules,
            compile=self.compile_rules,
        )

    #: Upstream selection rules.
    overrides = pilo.fields.List(pilo.fields.String(), ignore=None).tag('dynamic')

    @overrides.field.parse
    def overrides(self, path):
        value = path.primitive()
        if isinstance(value, Rule):
            return path.value
        try:
            return self.rule_parser(value)
        except exc.ParseException, ex:
            self.ctx.errors.invalid(str(ex))
            return pilo.ERROR

    @overrides.default
    def overrides(self):
        return Rules(
            auto_disable=self.auto_disable_rules,
            compile=self.compile_rules,
        )

    @overrides.munge
    def overrides(self, value):
        return Rules(
            value,
            auto_disable=self.auto_disable_rules,
            compile=self.compile_rules,
        )

    #: Dynamic configuration source.
    dynamic = pilo.fields.PolymorphicSubForm(Dynamic._type_, default=None)

    @property
    def upstream_parser(self):
        return parser.for_upstream()

    @property
    def rule_parser(self):
        return parser.for_rule(self.request_type)

    # match

    def match_me(self, request):
        """
        :param request:
        :return:
        """
        for host in self.hosts:
            m = host.match(request.host)
            if m:
                return m

    def match_upstream(self, request):
        """
        :param request:
        :return:
        """
        return (
            self.overrides.match(request) or
            self.rules.match(request) or
            self.default_upstream
        )

    # dynamic

    @property
    def is_dynamic(self):
        return self.dynamic is not None and self.dynamic.can_connect(self)

    def connect(self):

        @contextlib.contextmanager
        def _disconnect():
            try:
                yield
            finally:
                self.disconnect()

        if not self.is_dynamic:
            raise exc.RouterNotDynamic(self)
        self.dynamic.connect(self)
        return _disconnect()

    @property
    def is_connected(self):
        return self.is_dynamic and self.dynamic.is_connected(self)

    def disconnect(self):
        if self.is_connected:
            self.dynamic.disconnect(self)

    def load(self):
        if not self.is_connected:
            raise exc.RouterNotConnected(self)
        self.dynamic.load(self)

    def save(self):
        if not self.is_connected:
            raise exc.RouterNotConnected(self)
        self.dynamic.save(self)

    def watch(self, callback):
        if not self.is_connected:
            raise exc.RouterNotConnected(self)
        return self.dynamic.watch(self, callback)


try:
    from .redis import Redis
except ImportError, ex:
    logger.info('redis  dynamic unavailable - %s', ex)

try:
    from .zookeeper import Zookeeper
except ImportError:
    logger.info('zookeeper dynamic unavailable - %s', ex)
