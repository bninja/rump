import re
import setuptools
import sys


install_requires = [
    'netaddr >=0.7,<0.8',
    'pilo >=0.5,<0.6',
    'pyparsing >=2.0.1,<3.0',
]
if sys.version_info[0:2] < (2, 7):
    install_requires.append('ordereddict')

extras_require = {
    'kazoo': ['kazoo >=1.3.1,<2.0'],
    'redis': ['redis'],
    'gunicorn': [
        'gevent ==1.0',
        'gunicorn',
        'setproctitle >=1.1.8,<2.0',
    ],
}

extras_require['tests'] = [
    'mock >=1,<2',
    'pytest >=2.5.2,<3',
    'pytest-cov >=1.7,<2',
    'requests >=2.0,<3',
] + (
    extras_require['kazoo'] +
    extras_require['redis'] +
    extras_require['gunicorn']
)

setuptools.setup(
    name='rump',
    version=(
        re
        .compile(r".*__version__ = '(.*?)'", re.S)
        .match(open('rump/__init__.py').read())
        .group(1)
    ),
    url='https://github.com/bninja/rump/',
    author='Rump Us',
    author_email='ru@mp.us',
    license='MIT',
    description='Upstream selection.',
    long_description=open('README.rst').read(),
    platforms='any',
    install_requires=install_requires,
    extras_require=extras_require,
    tests_require=extras_require['tests'],
    packages=setuptools.find_packages('.', exclude=('test',)),
    scripts=['bin/rump', 'bin/rumpd'],
    include_package_data=True,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'License :: OSI Approved :: ISC License (ISCL)',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
    ],
    test_suite='nose.collector',
)
