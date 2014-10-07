====
rump
====

.. image:: https://travis-ci.org/bninja/rump.png
   :target: https://travis-ci.org/bninja/rump

.. image:: https://coveralls.io/repos/bninja/rump/badge.png
   :target: https://coveralls.io/r/bninja/rump


**Experimental** HTTP router.

dev
===

.. code:: bash

   $ git clone git@github.com:balanced/rump.git
   $ cd rump
   $ mkvirtualenv rump
   (rump)$ pip install -e .[tests]
   (rump)$ py.test tests/ --cov=rump --cov-report term-missing
