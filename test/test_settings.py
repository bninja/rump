import pytest

from rump import Settings, loads, dumps


@pytest.fixture
def settings_path(request):
    return request.config.fixtures_path.join('settings', 'main.conf')


def test_load(settings_path):
    settings = Settings.from_file(str(settings_path))
    assert len(settings.routers) == 3
    routers = sorted(settings.routers, key=lambda router: router.name)
    assert loads(dumps(routers)) == [
            {
                'name': 'router1',
                'compile_rules': True,
                'rules': [],
                'dynamic': None,
                'overrides': [],
                'enabled': True,
                'default_upstream': 'https://www.google.com,1',
                'request_type': 'rump.request:Request',
                'hosts': [
                    'google.'
                ],
                'auto_disable_rules': True
            }, {
                'name': 'router2',
                'compile_rules': True,
                'rules': [],
                'dynamic': {
                    'url': 'redis://localhost:6379/0',
                    'watch_timeout': 1.0,
                    '_type_': 'redis',
                    'key': 'test-router2',
                    'channel': 'test-router2'
                },
                'overrides': [],
                'enabled': True,
                'default_upstream': 'https://www.yahoo.com,1',
                'request_type': 'rump.request:Request',
                'hosts': [
                    'yahoo.'
                ],
                'auto_disable_rules': True
            }, {
                'name': 'router3',
                'compile_rules': False,
                'rules': [
                    'google in host => http://dev.google.com,1',
                    'yahoo in host => http://dev.yahoo.com,1',
                    'bing in host => http://dev.bing.com,1'
                ],
                'dynamic': {
                    'hosts': [
                        'localhost'
                    ],
                    '_type_': 'zookeeper',
                    'timeout': 15,
                    'root': 'test_router3'
                },
                'overrides': [],
                'enabled': True,
                'default_upstream': 'https://www.google.com,80 https://www.yahoo.com,15 https://www.bing.com,5',
                'request_type': 'rump.request:Request',
                'hosts': [
                    'dev.'
                ],
                'auto_disable_rules': True
            }
    ]


def test_load_one(settings_path):
    settings = Settings.from_file(str(settings_path), names=['router3'])
    assert loads(dumps(settings.routers)) == [{
        'name': 'router3',
        'compile_rules': False,
        'rules': [
            'google in host => http://dev.google.com,1',
            'yahoo in host => http://dev.yahoo.com,1',
            'bing in host => http://dev.bing.com,1'
        ],
        'dynamic': {
            'hosts': [
                'localhost'
            ],
            '_type_': 'zookeeper',
            'timeout': 15,
            'root': 'test_router3'
        },
        'overrides': [],
        'enabled': True,
        'default_upstream': 'https://www.google.com,80 https://www.yahoo.com,15 https://www.bing.com,5',
        'request_type': 'rump.request:Request',
        'hosts': [
            'dev.'
        ],
        'auto_disable_rules': True
    }]
