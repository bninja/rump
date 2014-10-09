"""
R(outing)Ump(ire) does upstream (i.e. server) selection for HTTP requests. It
does **not** proxy the request but instead should integrate with a
load-balancer or reverse-proxy that exposes an upstream selection interface
(e.g. nginx `X-Accel-* <http://wiki.nginx.org/X-accel>`_).

The idea is you to define a matching expression. This is can be done using a
simple expression language in Python:

.. code:: python

    exp = rump.and_(
        rump.Request.method.in_(['GET', 'POST']),
        rump.or_(Request.path.startwith('/v1/') Request.client_ip4 == '1.2.3.4')),
    )

or equivalently in a simple dsl:

.. code:: python

    parse = rump.parser.for_match()
    exp = parse('method in ["GET", "POST"] and (path startswith "/v1/" or client_ipv == 1.2.3.4)')
    assert isinstance(exp, rump.Expression)

to see the dsl representation for a Python expression just print it:

.. code:: python

    print exp

This expression can then be evaluated against the WSGI environment for a
request:

.. code:: python

    environ = {
        'METHOD': 'GET'
        'PATH_INFO': '/v1/hi/there?name=you'
        'REMOTE_ADDR': '1.2.3.4'
    }
    req = rump.Request(environ)
    print exp(req)

A rule links an expression to an upstream, which is just a weighted selection
of servers:

.. code:: python

    ups = rump.Upstream([
        ('https', 'one.me.org', 8),
        ('http', 'two.me.org', 2)
    ])
    rule = rump.Rule(exp, ups)
    if rule.match(req):
        server = rule.ups()

The only interesting thing here is that the request schema (represented by
`rump.Request`) is extensible and the dsl generate for that schema allows you
to write concise, domain specific rules:

.. code:: python

    import mystuff

    class MyRequest(rump.Request):

        env = rump.Request.String()

        @env.compute
        def env(self):
            if not self.authorized or not self.username:
                return 'public'
            user = mystuff.lookup(self.username)
            if not user:
                return 'unknown'
            if user.blacklisted:
                return 'bl'
            return user.env

    rules = rump.Rules([
        "env == bl => http://bl.i.com",
        "env == vip => http://vip-1.i.com http://vip-2.i.com http://vip-3.i.com",
        "env == sandbox => http://test.i.com",
        "env == public => http://open.i.com",
        ],
        request_type=MyRequest,
    )

Lastly all of this can be encapsulated in a router, possibly hooked to some
remote data store, and used like:

    .. code:: python

        router = rump.Router(
            name='my-router',
            request_type=MyRequest,
            rules=rules,
            dynamic=rump.router.Redis(
                key='my-router'
                channel='my-router'
            )
        )
        router.connect()
        router.watch(lambda x: x.reload())
        if router.match_host(req):
            ups = router.match_upstrem(req)
            server = ups()
            print server

"""
__version__ = '0.2.1'

import json


def loads(text):
    return json.loads(text)


def dumps(obj):

    def _default(obj):
        if isinstance(obj, (
               Upstream, Rule, Rule.compiled_type, types.IPNetwork
           )):
            return str(obj)
        if isinstance(obj, Rules):
            return list(obj)
        if hasattr(obj, 'pattern'):
            return obj.pattern
        if obj in (Request,):
            return '{0}:{1}'.format(obj.__module__, obj.__name__)
        raise TypeError(repr(obj) + ' is not JSON serializable')

    return json.dumps(obj, indent=4, default=_default)

from . import exc
from . import exp
from .exp import Expression, and_, or_, not_, types
from . import request
from .request import Request
from .rule import Rule, Rules
from .upstream import Upstream, Selection, Server
from . import parser
from . import router
from .router import Router, Dynamic
from .settings import Settings
from . import cli
from . import wsgi


__all__ = [
    'loads',
    'dumps',
    'exc',
    'exp',
    'Expression',
    'and_',
    'or_',
    'not_',
    'types',
    'request',
    'Request',
    'Rule',
    'Rules',
    'Upstream',
    'Selection',
    'Server',
    'parser',
    'Router',
    'Dynamic',
    'Settings',
    'wsgi',
    'cli',
]
