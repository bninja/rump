from __future__ import absolute_import

import logging
import threading

import etcd
import pilo
import urllib3

from .. import dumps, loads
from . import Dynamic


logger = logging.getLogger(__name__)


class EtcD(Dynamic):

    _type_ = pilo.fields.Type.instance('etcd')

    #: Cluster as a collection of host, port pairs.
    cluster = pilo.fields.List(
        pilo.fields.Tuple(pilo.fields.String(), pilo.fields.Integer(default=4001)),
        default=lambda: [('localhost', 4001)]
    )

    read_timeout = pilo.fields.Integer(default=60)

    allow_redirect = pilo.fields.Boolean(default=True)

    protocol = pilo.fields.String(default='http')

    allow_reconnect = pilo.fields.Boolean(default=False)

    key = pilo.fields.String()

    # Dynamic

    def can_connect(self, router):
        return True

    def connect(self, router):
        logger.info('connecting to %s', self.cluster)
        self._cli = etcd.Client(
            host=tuple(self.cluster),
            read_timeout=self.read_timeout,
            allow_redirect=self.allow_redirect,
            protocol=self.protocol,
            allow_reconnect=self.allow_reconnect,
        )

    def is_connected(self, router):
        return self._cli is not None

    def disconnect(self, router):
        logger.info('disconnecting from %s', self.cluster)
        if self._watch_thd:
            if self._watch_thd.is_alive():
                self._watch_thd.stop()
            self._watch_thd = None
        self._cli = None

    def load(self, router):
        src = self._src(router)
        update = type(router)()
        update.map(src, tags=['dynamic'], error='raise')
        router.update(update)

    def save(self, router):
        self._write(router.filter('dynamic'))

    def watch(self, router, callback):

        logger.info('watching key %s', self.key)
        self._watch_thd = self._WatchThread(
            cli=self._cli, key=self.key, callback=callback, router=router,
        )
        self._watch_thd.daemon = True
        self._watch_thd.start()

    # internals

    _cli = None

    _watch_thd = None

    class _WatchThread(threading.Thread):

        def __init__(self, cli, key, callback, router, timeout=None):
            threading.Thread.__init__(self)
            self.cli = cli
            self.key = key
            self.callback = callback
            self.router = router
            self.timeout = timeout

        def run(self):
            while not self.stopped:
                try:
                    logger.info('watching %s', self.key)
                    self.cli.watch(self.key, timeout=self.timeout)
                except urllib3.exceptions.TimeoutError:
                    logger.debug('watch %s timed out', self.key)
                logger.info('%s changed')
                callback = self.callback
                if callback is not None:
                    callback(self.router)
            logger.info('stopped watching %s', self.key)

        @property
        def stopped(self):
            return self.callback is None

        def stop(self):
            self.callback = None

    def _src(self, router):
        srcs = []
        value = self._read()
        if value is not None:
            srcs.append(pilo.source.DefaultSource(value))
        srcs.append(router)
        return pilo.source.union(srcs)

    def _read(self):
        try:
            text = self._cli.read(self.key).value
            logger.info('read from %s\n%s', self.key, text)
        except KeyError:
            logger.info('%s does not exist', self.key)
            return
        return loads(text)

    def _write(self, value):
        text = dumps(value)
        logger.info('writing to %s\n%s', self.key, text)
        self._cli.write(self.key, text)
