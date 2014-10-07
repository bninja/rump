import ConfigParser
import glob
import logging
import os

import pilo

from . import Router, Dynamic


logger = logging.getLogger(__name__)


class Settings(pilo.Form):
    """
    Router settings read from ini-style configuration files. Typically used like:

    .. code:: python

        settings = rump.Settings.from_file('~/.rump/rump.conf',)
        print settings

    which might look like:

    .. code:: ini

        [rump]
        includes = ./*.conf

        [router1]
        hosts = google\.
        default_upstream = https://www.google.com

        [router2]
        hosts = yahoo\.
        default_upstream = https://www.yahoo.com
        dynamic = redis

        [router2:redis]
        key = test-router2
        channel = test-router2

    """

    #: Look for routers in these files or globs.
    includes = pilo.fields.List(pilo.fields.String())

    @includes.field.munge
    def includes(self, value):
        if not self.ctx.src_path.location:
            return value
        prev = os.getcwd()
        try:
            os.chdir(os.path.dirname(self.ctx.src_path.location))
            return os.path.abspath(value)
        finally:
            os.chdir(prev)

    @includes.munge
    def includes(self, value):
        if self.ctx.src_path.location:
            # NOTE: include self in globs.
            value = [self.ctx.src_path.location] + value
        return value

    @includes.default
    def includes(self):
        return (
            [self.ctx.src_path.location] if self.ctx.src_path.location else []
        )

    #: Routers loaded from globed includes.
    routers = pilo.fields.List(pilo.Field())

    @routers.compute
    def routers(self):
        names = getattr(self.ctx, 'names', None)
        main = getattr(self.ctx, 'main', None)
        routers = []
        globed = set()
        for include in self.includes:
            logger.debug('globing for %s', include)
            for file_path in glob.iglob(include):
                file_path = os.path.abspath(file_path)
                if os.path.isdir(file_path):
                    logger.debug('skipping directory %s', file_path)
                    continue
                if file_path in globed:
                    logger.debug('skipping duplicate glob %s', file_path)
                    continue
                globed.add(file_path)
                logger.info('loading router(s) from %s', file_path)
                config_parser = ConfigParser.ConfigParser()
                config_parser.read(file_path)
                for section in config_parser.sections():
                    if ':' in section:
                        continue
                    if main and main == section:
                        continue
                    if names and section not in names:
                        logger.debug('skipping router %s from %s', file_path)
                        continue
                    with self.ctx.reset():
                        router = load_router(config_parser, section, file_path)
                    routers.append(router)
        return sorted(routers, key=lambda router: router.name)

    @classmethod
    def from_file(cls, file_path, section=None, names=None):
        if not os.path.isfile(file_path):
            raise ValueError('{0} is not a file'.format(file_path))
        logger.info('loading settings from %s', file_path)
        config_parser = ConfigParser.ConfigParser()
        config_parser.read(file_path)
        return cls.from_config(
            config_parser, file_path=file_path, section=section, names=names,
        )

    @classmethod
    def from_config(cls,
                    config_parser,
                    section=None,
                    file_path=None,
                    names=None,
        ):
        section = section or 'rump'
        with pilo.ctx(names=names, main=section):
            return cls(pilo.source.ConfigSource(
                config_parser, section=section, location=file_path,
            ))


def load_router(config_parser, section, file_path=None):
    """
    Loads one router from an ini-style configuration file(s).

    :param config_parser: Parsed ini-style configuration file(s).
    :param section: Section to read router from. This also the **name** of the
                    router.
    :param file_path: Optional location of ini-style configuration file which
                      is helpful for showing source of validation errors.
    :return: The router (typically an instance of ``rump.Router``).
    """
    # probe

    dynamics = []
    for dynamic in sorted(pilo.Types.map(Dynamic._type_).keys()):
        dynamic_section = '{0}:{1}'.format(section, dynamic)
        if config_parser.has_section(dynamic_section):
            dynamics.append(dynamic)
    logger.debug('available dynamics %s for %s', dynamics, section)

    class _Probe(pilo.Form):

        class_ = pilo.fields.Code('class', default=lambda: Router)

        dynamic = pilo.fields.String(choices=dynamics, ignore='', default=None)

    probe = _Probe(
        pilo.source.ConfigSource(config_parser, section, location=file_path)
    )

    # source

    srcs = [{'name': section}]
    if probe.dynamic:
        dynamic_section = '{0}:{1}'.format(section, probe.dynamic)
        logger.debug(
            'loading dynamic settings %s in %s', dynamic_section, file_path,
        )
        srcs.append(pilo.source.mount(dynamic=pilo.source.union([
            {'_type_': probe.dynamic},
            pilo.source.ConfigSource(
                config_parser, dynamic_section, location=file_path,
            ),
        ])))
    else:
        logger.debug('no dynamic settings for %s in %s', section, file_path)
        srcs.append(pilo.source.mount(dynamic=None))
    srcs.append(
        pilo.source.ConfigSource(config_parser, section, location=file_path)
    )
    src = pilo.source.union(srcs)

    return probe.class_(src)
