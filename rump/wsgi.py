"""
Example WSGI application showing remote integration for:

- nginx `X-Accel-* <http://wiki.nginx.org/X-accel>`_
- ...

If you installed rump you can just do:

.. code:: bash

    $ rump serve -ld

"""
import errno
import logging
import netaddr
import os
import pprint
import socket
import StringIO
import threading
import wsgiref.simple_server

import coid
import ohmr
import pilo

import rump


__all__ = [
    'app',
]


logger = logging.getLogger(__name__)

tracer = ohmr.Tracer(coid.Id(prefix='ohm-', encoding='base58'))


class Request(pilo.Form):

    def __init__(self, environ, id_header):
        super(Request, self).__init__()
        self.environ = environ
        self.src = pilo.source.DefaultSource(environ)
        self.id_header = 'HTTP_' + id_header.upper().replace('-', '_')

    host = pilo.fields.String('HTTP_HOST')

    method = pilo.fields.String('REQUEST_METHOD')

    path = pilo.fields.String('PATH_INFO')

    query_string = pilo.fields.String('QUERY_STRING')

    id = pilo.fields.String(default=lambda: tracer.id)

    @id.resolve
    def id(self):
        return self.ctx(src=self.id_header)

    echo = pilo.fields.Boolean('HTTP_X_RUMP_ECHO', default=False)

    redirect_prefix = pilo.fields.String('HTTP_X_RUMP_PREFIX', default='/rump')

    default_upstream = pilo.fields.String('HTTP_X_RUMP_REDIR_DEFAULT', default=None)

    @default_upstream.parse
    def default_upstream(self, path):
        value = path.primitive()
        if isinstance(value, rump.Upstream):
            return value
        parse = rump.parser.for_upstream()
        try:
            return parse(value)
        except rump.exc.ParseException, ex:
            self.ctx.errors.invalid(str(ex))

    forwards = pilo.fields.String('HTTP_X_RUMP_FORWARD', default=None)

    hosts = pilo.fields.String('HTTP_X_RUMP_HOST', default=None)

    @classmethod
    def read(cls, io):
        """
        Generator used to parse and yield HTTP requests from file-like object.

        :param io: File-like object to read HTTP requests from
        """

        class _Server(wsgiref.simple_server.WSGIServer):

            def server_activate(self):
                pass

        class _Handler(wsgiref.simple_server.WSGIRequestHandler):

            def setup(self):
                self.rfile = io
                self.wfile = StringIO.StringIO()

            def handle(self):
                pass

            def finish(self):
                pass

        dummy = _Handler(
            None,
            ('127.0.0.1', 0),
            server=_Server(('127.0.0.1', 0), _Handler, True)
        )

        while True:
            dummy.raw_requestline = io.readline()
            if not dummy.raw_requestline:
                break
            dummy.parse_request()
            environ = dummy.get_environ()
            request = cls(environ, app.settings.id_header)
            yield request


class Settings(pilo.Form):

    def from_file(self, path):
        logger.info('loading settings from %s', path)
        src = pilo.source.union([
            pilo.source.ConfigSource.from_file(path, 'rump:wsgi'),
            {'routers': rump.Settings.from_file(path, 'rump').routers},
            self,
        ])
        settings = type(self)(src)
        self.update(settings)
        logger.debug('loaded settings\n%s', rump.dumps(settings))
        return settings

    def from_env(self):
        file_path = os.getenv('RUMP_CONF_FILE')
        if not file_path:
            logger.info('no settings @ RUMP_CONF_FILE=')
            for file_path in ['./rump.conf', '~/.rump', '/etc/rump/rump.conf']:
                file_path = os.path.abspath(file_path)
                if os.path.isfile(file_path):
                    break
                logger.info('no settings @ %s', file_path)
            else:
                file_path = None
        if file_path is None:
            raise LookupError('Unable to locate settings file')
        return self.from_file(file_path)

    #: Id header (e.g. X-MyOrg-Id).
    id_header = pilo.fields.String(default='X-Rump-Id')

    #: Path to health file.
    health_file = pilo.fields.String(default=None)

    #: List of routers.
    routers = pilo.fields.List(pilo.fields.SubForm(rump.Router), default=list)

    #: List of proxy CIDRs.
    proxies = pilo.fields.List(pilo.fields.String(), default=list)

    @proxies.field.validate
    def proxies(self, value):
        try:
            netaddr.IPNetwork(value)
        except (netaddr.AddrFormatError,), ex:
            self.errors.invalid(str(ex))
            return False
        return True

    @proxies.field.munge
    def proxies(self, value):
        return netaddr.IPNetwork(value)


class _Application(threading.local):

    #: Global name of this host.
    host = socket.gethostname()

    #: Global settings.
    settings = Settings()

    #: Local WSGI environment for request being handled now.
    environ = None

    #: Local wrapper for request being handled now.
    request = None

    def setup(self):
        logger.info('setup')
        for router in self.settings.routers:
            if router.is_dynamic:
                logger.info('connecting %s', router.name)
                router.connect()
                router.watch(self.changed)

    def teardown(self):
        logger.info('teardown')
        for router in self.settings.routers:
            if router.is_connected:
                logger.info('disconnecting %s', router.name)
                router.disconnect()

    def changed(self, router):
        logger.info('%s changed, reloading ...', router.name)
        router.load()
        logger.info('%s', rump.dumps(router))

    def router_for(self, request=None):
        request = self.request if request is None else request
        for router in self.settings.routers:
            if router.match_me(request):
                return router

    def __call__(self, environ, start_response):
        self.environ = environ
        self.request = Request(environ, self.settings.id_header)
        try:
            if self.request.path == '/health':
                status, headers, body = health()
            elif self.request.path == '/boom':
                status, headers, body = boom()
            else:
                status, headers, body = select()
        except (SystemExit, KeyboardInterrupt):
            raise
        except Exception, ex:
            logger.exception(ex)
            body = str(ex)
            status = '500 Internal Server Error'
            headers = [
                ('Content-Type', 'text/plain'),
                ('Content-Length', str(len(body))),
            ]
        headers.append((self.settings.id_header, self.request.id.encode('utf-8')))
        headers.append(('X-Rump-Version', rump.__version__))
        start_response(status, headers)
        self.request = None
        return body


app = _Application()


def health():
    """
    Indicates whether this instance is up (status 200) not (status 503).
    """
    headers = [
        ('Content-Type', 'text/plain'),
    ]
    if app.settings.health_file:
        try:
            with open(app.settings.health_file, 'r') as fo:
                body = fo.read()
            status = '200 OK'
        except IOError, ex:
            if ex.errno != errno.ENOENT:
                raise
            body = 'down'
            status = '503 Service Unavailable'
    else:
        status = '200 OK'
        body = ''
    headers.append(('Content-Length', str(len(body))))
    return status, headers, [body]


def boom():
    """
    Used to test error/exception side-effects (e.g. logging, alerting, etc).
    """
    raise NameError("name 'ka' is not defined")


def select():
    """
    Selects upstream.
    """
    # select server
    router = app.router_for(app.request)
    if not router:
        raise Exception(
            'No router for request:\n{0}'
            .format(pprint.pformat(app.environ))
        )
    request = router.request_type(app.environ, router)
    upstream = router.match_upstream(request)
    if upstream is None:
        upstream = app.request.default_upstream or router.default_upstream
    server = upstream() if upstream else None
    if not server:
        raise Exception(
            'No upstream for request:\n{0}\nand router:\n{1}'
            .format(pprint.pformat(app.environ), pprint.pformat(router))
        )

    # communicate selection
    status, headers, body = x_accel(server)

    # x-forward-for
    forwards = '{0}://{1}'.format(server.protocol, server.location)
    if app.request.forwards:
        forwards = app.request.forwards + ', ' + forwards

    # x-rump-host
    hosts = app.host
    if app.request.hosts:
        hosts = app.request.hosts + ', ' + hosts

    headers.extend([
       ('X-Rump-Redir-Proto', server.protocol),
       ('X-Rump-Redir-Host', server.location),
       ('X-Rump-Forward', forwards),
       ('X-Rump-Host', hosts),
    ])

    return status, headers, body


def x_accel(server):
    """
    Constructs X-Accel internal-redirect response for the selected server.
    """
    status = '200 OK'
    headers = []
    path = app.request.path
    if not path.startswith('/'):
        path = '/' + path
    if app.request.query_string:
        path += '?' + app.request.query_string
    redirect = app.request.redirect_prefix + path
    if not app.request.echo:
        headers.append(('X-Accel-Redirect', redirect))
        body = []
    else:
        body = redirect
        headers.extend([
            ('Content-Type', 'text/plain'),
            ('Content-Length', str(len(body)))
        ])
        body = [body]
    return status, headers, body
