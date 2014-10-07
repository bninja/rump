from __future__ import absolute_import

import ConfigParser
import functools
import logging
import os
import StringIO

from kazoo.client import KazooClient

import pilo

from .. import Upstream, Rule, Rules
from . import Dynamic


logger = logging.getLogger(__name__)


class Zookeeper(Dynamic):

    _type_ = pilo.fields.Type.instance('zookeeper')

    #: List of hosts where dynamic configuration is stored.
    hosts = pilo.fields.List(pilo.fields.String(), min_length=1, default=lambda: ['localhost'])

    #: Seconds to wait for a response when communicating with hosts.
    timeout = pilo.fields.Integer(min_value=1, default=15)

    #: Path to root node where dynamic configuration is stored.
    root = pilo.fields.String()

    # Dynamic

    def can_connect(self, router):
        return self.hosts and self.root is not None

    def connect(self, router):
        logger.info('connecting to %s ...', self.hosts)
        cli = KazooClient(hosts=','.join(self.hosts))
        cli.start(timeout=self.timeout)
        self._cli = cli

    def is_connected(self, router):
        return self._cli is not None

    def disconnect(self, router):
        logger.info('disconnecting from %s ...', self.hosts)
        self._cli.stop()
        self._cli = None

    def load(self, router):
        src = self._src(router)
        update = type(router)()
        update.map(src, tags=['dynamic'], error='raise')
        router.update(update)

    def save(self, router):
        self._set_overrides(router)
        self._set_config(router)

    def watch(self, router, callback):

        def _intercept(watch, data, stat):
            watch._func = _relay

        def _relay(data, stat):
            return callback(router)

        for path in [self._config_path, self._overrides_path]:
            self._cli.ensure_path(path)
            logger.info('watching %s ...', path)
            watch = self._cli.DataWatch(path)
            # NOTE: replaces _intercept w/ _relay
            watch(functools.partial(_intercept, watch))

    # internals

    _cli = None

    def _src(self, router):
        srcs = []

        # settings
        config = self._get_config(router)
        if config is not None:
            srcs.append(pilo.source.ConfigSource(
                config, section=router.name, location=self._config_path
            ))

        # overrides
        raw = self._get_overrides()
        if raw is not None:
            srcs.append({'overrides': raw})

        # fallback
        srcs.append(router)

        return pilo.source.UnionSource(srcs)

    @property
    def _config_path(self):
        return os.path.join(self.root, 'config')

    def _get_config(self, router):
        if not self._cli.exists(self._config_path):
            return
        raw, stat = self._cli.get(self._config_path)
        config = ConfigParser.ConfigParser()
        config.readfp(StringIO.StringIO(raw))
        if not config.has_section(router.name):
            return
        return config

    def _encode_config(self, value):
        if isinstance(value, (int, long, basestring, float, bool)):
            return str(value)
        if hasattr(value, 'pattern'):
            return self._encode_config(value.pattern)
        if isinstance(value, (Upstream, Rule)):
            return str(value)
        if isinstance(value, (Rules,)):
            return value.dumps()
        if isinstance(value, list):
            return ', '.join(self._encode_config(v) for v in value)
        raise TypeError('Cannot encode {0!r}'.format(value))

    def _set_config(self, router):
        self._cli.ensure_path(self._config_path)
        config = ConfigParser.ConfigParser()
        config.add_section(router.name)
        for field in router.fields:
            if not 'dynamic' in field.tags or field.name == 'overrides':
                continue
            value = self._encode_config(field.__get__(router))
            config.set(router.name, field.src, value)
        fo = StringIO.StringIO()
        config.write(fo)
        self._cli.set(self._config_path, fo.getvalue())

    @property
    def _overrides_path(self):
        return os.path.join(self.root, 'overrides')

    def _get_overrides(self):
        if not self._cli.exists(self._overrides_path):
            return
        raw, stat = self._cli.get(self._overrides_path)
        return raw.splitlines() or None

    def _set_overrides(self, router):
        if 'dynamic' not in type(router).overrides.tags:
            return
        self._cli.ensure_path(self._overrides_path)
        self._cli.set(self._overrides_path, router.overrides.dumps())
