====
rump
====

.. image:: https://travis-ci.org/bninja/rump.png
   :target: https://travis-ci.org/bninja/rump

.. image:: https://coveralls.io/repos/bninja/rump/badge.png
   :target: https://coveralls.io/r/bninja/rump

R(outing)Ump(ire) is an **experimenal** upstream (i.e. server) selector for
HTTP requests. It does **not** proxy the request but instead integrates with a
load-balancer or reverse-proxy that exposes an upstream selection interface:

- nginx `X-Accel-* <http://wiki.nginx.org/X-accel>`_
- ...

dev
===

.. code:: bash

   $ git clone git@github.com:bninja/rump.git
   $ cd rump
   $ mkvirtualenv rump
   (rump)$ pip install -e .[tests]
   (rump)$ py.test test/ --cov=rump --cov-report term-missing

wtf?
====

Typically you can embed complex routing logic directly in a load-balancer or
reverse-proxy (e.g. nginx lua, varnish vcl, etc) and that's what should be
done 99% of the time.

This is an **experiment** to see what writing a Python based HTTP upstream
selector would look like and what flexibility that gives you.

Use it as a ``program`` or embed it as a ``lib`` in your proxy.

program
=======

Install it:

- `ansible-rump <https://github.com/bninja/ansible-rump>`_
- ...

Use it:

.. code:: bash

   $ rump list
   my-router
   $ rump show -d my-router
   ...
   $ rump edit -d my-router
   $ service rumpd status


lib
===

Get it:

.. code:: bash

   $ pip install rump
    
    
Use it:

.. code:: python

   import rump
   
   router = rump.Router(
       name='my-router',
       ...
   )

   upstream = router.match_upstream(router.request_type(wsgi_environ))
   if upstream:
      server = upstream()
