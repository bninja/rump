from __future__ import absolute_import

import logging

import pilo
import redis

from .. import dumps, loads
from . import Dynamic


logger = logging.getLogger(__name__)


class Redis(Dynamic):

    _type_ = pilo.fields.Type.instance('redis')

    #: Connection string.
    url = pilo.fields.String(default='redis://localhost:6379/0')

    #: Pub/sub channel.
    channel = pilo.fields.String()

    #: Store key.
    key = pilo.fields.String()

    #: Number of seconds between each watch.
    watch_timeout = pilo.fields.Float(default=1.0)

    # Dynamic

    def can_connect(self, router):
        return True

    def connect(self, router):
        logger.info('connecting to %s', self.url)
        cli = redis.Redis.from_url(self.url)
        pubsub = cli.pubsub()
        self._cli, self._pubsub, self._subthd = cli, pubsub, None

    def is_connected(self, router):
        return self._cli is not None

    def disconnect(self, router):
        logger.info('disconnecting from %s', self.url)
        if self._subthd:
            self._subthd.stop()
            self._subthd = None
        if self._pubsub:
            self._pubsub.close()
            self._pubsub = None
        self._cli = None

    def load(self, router):
        src = self._src(router)
        update = type(router)()
        update.map(src, tags=['dynamic'], error='raise')
        router.update(update)

    def save(self, router):
        self._set(router)

    def watch(self, router, callback):
        logger.info('subscribing to channel %s', self.channel)
        self._pubsub.subscribe(**{
            self.channel: lambda message: callback(router)
        })
        if self._subthd is None or not self._subthd.active():
            self._subthd = self._pubsub.run_in_thread(
                sleep_time=self.watch_timeout,
            )

    # internals

    _cli = None

    _pubsub = None

    _subthd = None

    def _src(self, router):
        srcs = []

        # remote
        text = self._get(router)
        if text is not None:
            srcs.append(pilo.source.DefaultSource(text, location=self.key))

        # local
        srcs.append(router)

        return pilo.source.union(srcs)

    def _get(self, router):
        logger.info('getting key %s', self.key)
        text = self._cli.get(self.key)
        return loads(text) if text is not None else None

    def _set(self, router):
        dynamic = router.filter('dynamic')
        text = dumps(dynamic)
        logger.info('setting key %s\n%s', self.key, text)
        self._cli.set(self.key, text)

        logger.info('publishing to channel %s', self.channel)
        self._cli.publish(self.channel, text)
