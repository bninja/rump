"""
Commands for interacting w/ a rump install. These are exposed by bin/rump, so:

.. code:: bash

    $ rump --help

"""
import argparse
import logging
import os
import pprint
import SocketServer
import subprocess
import sys
import tempfile
import threading
import time
import wsgiref.simple_server

import pilo

import rump


__all__ = [
    'parser',
]


logger = logging.getLogger(__name__)


def conf_files():
    cands = ['./rump.conf', '~/.rump', '/etc/rump/rump.conf']
    paths = []
    for path in cands:
        path = os.path.abspath(path)
        if os.path.isfile(path):
            paths.append(path)
    return paths


def env():
    return {
        'log_level': os.getenv('RUMP_LOG_LEVEL'),
        'conf_file': os.getenv('RUMP_CONF_FILE', (conf_files() or [None])[0]),
    }


def parser(log_level=None, conf_file=None):
    root = argparse.ArgumentParser(add_help=False)
    root.add_argument(
        '-l', '--log', '--log-level',
        dest='log_level',
        choices=LogLevelAction.mapping.keys(),
        metavar='LEVEL',
        action=LogLevelAction,
        default=log_level,
    )
    root.add_argument(
        '-c', '--conf-file',
        metavar='FILE',
        default=conf_file,
    )
    root.add_argument(
        '-d', '--dynamic',
        action='store_true',
        default=False,
        help='load dynamic router configurations.',
    )
    root.set_defaults(setup=setup)
    root.set_defaults(settings=None)

    parser = argparse.ArgumentParser(
        parents=[root],

    )
    parser.add_argument(
        '-v', '--version',
        action='version',
        default=argparse.SUPPRESS,
        version=rump.__version__,
        help="show program's version number and exit",
    )

    commands = parser.add_subparsers(title='commands')
    list_parser(commands, [root])
    show_parser(commands, [root])
    edit_parser(commands, [root])
    watch_parser(commands, [root])
    check_parser(commands, [root])
    upstream_parser(commands, [root])
    serve_parser(commands, [root])

    return parser


class LogLevelAction(argparse.Action):

    mapping = {
        'd': logging.DEBUG, 'debug': logging.DEBUG,
        'i': logging.INFO, 'info': logging.INFO,
        'w': logging.WARNING, 'warn': logging.WARNING,
        'e': logging.ERROR, 'err': logging.ERROR, 'error': logging.ERROR,
    }

    def __call__(self, parser, namespace, values, option_string=None):
        if isinstance(values, list):
            values = [self.mapping[v] for v in values]
        else:
            values = self.mapping[values]
        setattr(namespace, self.dest, values)


def setup(args):
    logging.basicConfig(
        level=args.log_level,
        format='%(asctime)s : %(levelname)s : %(name)s : %(message)s',
        stream=sys.stderr,
    )
    if args.auto_load_settings:
        args.settings = rump.Settings.from_file(args.conf_file)
    if args.dynamic:
        for router in args.settings.routers:
            if router.is_dynamic:
                with router.connect():
                    router.load()


def router_with_name(routers, name):
    for router in routers:
        if router.name == name:
            return router
    raise LookupError('No router with name {0}'.format(name))


def check(conf_file, name):
    settings = rump.Settings.from_file(conf_file, names=[name])
    router_with_name(settings.routers, name)


def edit(router, io=None):
    if not router.is_dynamic:
        raise ValueError('Router {0} is not dynamic'.format(router.name))

    # editor
    if io is None:
        # select
        editors = ['VISUAL', 'EDITOR']
        for name in editors:
            editor = os.getenv(name, None)
            if editor:
                break
        else:
            raise RuntimeError(
                'Must define one of {0}'.format('=, '.join(editors))
            )
        logger.debug('using editor - %s', editor)

        # existing
        text = rump.dumps(router.filter('dynamic'))
        raw_fd, raw_path = tempfile.mkstemp(prefix='rump-')
        ctime = os.stat(raw_path).st_mtime
        with os.fdopen(raw_fd, 'w') as raw_fo:
            raw_fo.write(text)
        edit = [editor, raw_path]
        logger.debug('editing w/ - %s', ' '.join(edit))

        # edit it
        subprocess.check_call(edit)
        if os.stat(raw_path).st_mtime == ctime:
            logger.debug('no edits detected, aborting')
            os.remove(raw_path)
            return False
        io = open(raw_path, 'r')

    # validate
    src = pilo.source.union([
        pilo.source.JsonSource(io.read()),
        router,
    ])
    router = type(router)(src)

    # persist
    with router.connect():
        router.save()

    return True


def watch(routers, timeout=None, notifications=None, poll=1.0):
    count = []
    finished = threading.Event()

    def _callback(router):
        print 'router changed -', router.name
        count.append(1)
        if sum(count) >= notifications:
            finished.set()

    for router in routers:
        router.connect()
    try:
        for router in routers:
            router.watch(_callback)

        logging.info(
            'watching %s - timeout=%s, notifications=%s',
            ', '.join(router.name for router in routers), timeout, notifications,
        )
        expires_at = time.time() + timeout if timeout else None
        while not finished.is_set():
            finished.wait(poll)
            if expires_at and expires_at < time.time():
                logger.info('timed out')
                break
    finally:
        for router in routers:
            router.disconnect()


def eval_requests(routers, io, default_router=None):
    for request in rump.wsgi.Request.read(io):
        for router in routers:
            if router.match_me(request):
                break
        else:
            if default_router is None:
                logger.warning(
                   'no router for - \n%s', pprint.pformat(request.environ)
                )
                continue
            router = default_router
        upstream = router.match_upstream(router.request_type(request.environ))
        if upstream is None:
            logger.warning(
               'router %s has no upstream for - \n%s',
               router.name, pprint.pformat(request.environ)
            )
            continue
        logger.debug(
           'router %s matched upstream %s for - \n%s',
           router.name, upstream, pprint.pformat(request.environ)
        )
        server = upstream()
        print '{0}://{1}'.format(server.protocol, server.location)


def server_for(host, port, mode=None):
    if mode == 'thread':

        class server_cls(
                  SocketServer.ThreadingMixIn,
                  wsgiref.simple_server.WSGIServer,
              ):
            pass

    elif mode == 'fork':

        class server_clsserver_cls(
                  SocketServer.ForkingMixIn,
                  wsgiref.simple_server.WSGIServer,
              ):

            pass

    else:
        server_cls = wsgiref.simple_server.WSGIServer

    return wsgiref.simple_server.make_server(
        host=host, port=port, app=rump.wsgi.app, server_class=server_cls,
    )


# commands

def list_parser(commands, parents):
    command = commands.add_parser(
        'list',
        parents=parents,
        description='List routers.',
    )
    command.set_defaults(command=list_command, auto_load_settings=True)
    return command


def list_command(args):
    for router in args.settings.routers:
        print router.name


def show_parser(commands, parents):
    command = commands.add_parser(
        'show',
        parents=parents,
        description='Show router.',
    )
    command.add_argument(
        'name', help='router name.',
    )
    command.set_defaults(command=show_command, auto_load_settings=True)
    return command


def show_command(args):
    router = router_with_name(args.settings.routers, args.name)
    print rump.dumps(router)


def edit_parser(commands, parents):
    command = commands.add_parser(
        'edit',
        parents=parents,
        description='Edit router dynamic configuration.',
    )
    command.add_argument(
        'name', help='router name',
    )
    command.add_argument(
        'file', nargs='?', help='file to read from',
    )
    command.set_defaults(command=edit_command, auto_load_settings=True)
    return command


def edit_command(args):
    if not args.file:
        if sys.stdin.isatty():
            io = None
        else:
            io = sys.stdin
    else:
        io = open(args.file, 'r')
    edit(router_with_name(args.settings.routers, args.name), io)


def check_parser(commands, parents):
    command = commands.add_parser(
        'check',
        parents=parents,
        description="Checks a router's configuration.",
    )
    command.add_argument(
        'name', help='router name',
    )
    command.set_defaults(command=check_command, auto_load_settings=False)
    return command


def check_command(args):
    check(args.conf_file, args.name)
    return 0


def watch_parser(commands, parents):
    command = commands.add_parser(
        'watch',
        parents=parents,
        description='Watch router for changes.',
    )
    command.add_argument(
        'names', nargs='*', help='router names',
    )
    command.add_argument(
        '-n', '--notifications',
        type=int,
        help='exit after this many notifications',
    )
    command.add_argument(
        '-t', '--timeout',
        type=int,
        help='exit after this many seconds',
    )
    command.set_defaults(command=watch_command, auto_load_settings=True)
    return command


def watch_command(args):
    if args.names:
        routers = [
            router_with_name(args.settings.routers, name)
            for name in args.names
        ]
    else:
        routers = [
            router for router in args.settings.routers if router.is_dynamic
        ]
    watch(routers, args.timeout, args.notifications)


def upstream_parser(commands, parents):
    command = commands.add_parser(
        'eval',
        parents=parents,
        description='Evalulate HTTP requests for upstream.',
    )
    command.add_argument(
        'names', nargs='?', help='router names',
    )
    command.add_argument(
        '-r', '--requests',
        default='-',
        help='HTTP requests FILE, or - to read from stdin',
    )
    command.set_defaults(command=eval_command, auto_load_settings=True)
    return command


def eval_command(args):
    routers = (
        [router_with_name(args.settings.routers, name) for name in args.names]
        if args.names
        else args.settings.routers
    )
    io = (
        sys.stdin
        if args.requests == '-'
        else open(args.requests, 'r')
    )
    eval_requests(routers=routers, io=io)


def serve_parser(commands, parents):
    command = commands.add_parser(
        'serve',
        parents=parents,
        description='Serve upstream selection.',
    )
    command.add_argument(
        'names', nargs='?', help='router names',
    )
    command.add_argument(
        '--host', default='127.0.0.1',
    )
    command.add_argument(
        '-p', '--port', type=int, default=4114,
    )
    command.add_argument(
        '-f', '--forking', action='store_true', default=False,
    )
    command.add_argument(
        '-t', '--threading', action='store_true', default=False,
    )
    command.set_defaults(command=serve_command, auto_load_settings=False)
    return command


def serve_command(args):
    if args.conf_file is not None:
        rump.wsgi.app.settings.from_file(args.conf_file)
    rump.wsgi.app.setup()

    mode = None
    if args.forking:
        mode = 'fork'
    if args.forking:
        mode = 'thread'
    server = server_for(host=args.host, port=args.port, mode=mode,)
    logger.info('serving on {0}:{1} ...'.format(*server.server_address))
    try:
        server.serve_forever()
    finally:
        logger.info('exited')
        rump.wsgi.app.teardown()
