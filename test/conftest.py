import logging
import os

import py


def pytest_configure(config):
    logging_level = {
        'd': logging.DEBUG, 'debug': logging.DEBUG,
        'i': logging.INFO, 'info': logging.INFO,
        'w': logging.WARN, 'warn': logging.WARN,
    }[os.environ.get('RUMP_TEST_LOG', 'w').lower()]
    logging.basicConfig(level=logging_level)
    config.fixtures_path = py.path.local(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'fixtures',
    ))
