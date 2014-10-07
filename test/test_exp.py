from rump import Request, types, and_, or_, not_


def test_str():
    cases = [
        (Request.client_ip4.in_(types.IPNetwork('1/8')),
         'client_ip4 in 1.0.0.0/8'),
        (Request.client_ip4.in_(types.IPNetwork('1/8')) &
         (Request.method == 'GET'),
         'client_ip4 in 1.0.0.0/8 and method = "GET"'),
        (Request.client_ip4.in_(types.IPNetwork('1/8')) |
         (Request.method == 'GET'),
         'client_ip4 in 1.0.0.0/8 or method = "GET"'),
        (Request.client_ip4 != types.IPAddress('1.2.3.4'),
         'client_ip4 != 1.2.3.4'),
        (Request.path.match('/v[1234]/resources'),
         'path ~ "/v[1234]/resources"'),
        (~Request.path.match('/v[1234]/resources'),
         'path !~ "/v[1234]/resources"'),
    ]
    for case, expected in cases:
        assert str(case) == expected


def test_compile():
    cases = [
        Request.client_ip4.in_(types.IPNetwork('1/8')),
        Request.client_ip4.in_(types.IPNetwork('1/8')) & (Request.method == 'GET'),
        Request.client_ip4.in_(types.IPNetwork('1/8')) | (Request.method == 'GET'),
        Request.client_ip4 != types.IPAddress('1.2.3.4'),
        Request.path.match('/v[1234]/resources'),
        Request.path.startswith('/veep/'),
        Request.path.endswith('/'),
        Request.path.contains('veep'),
        Request.content_length < 100,
        Request.content_length >= 100,
        Request.has_content,
    ]
    for case in cases:
        assert case.compile(case.symbols())


def test_traverse():
    e = and_(
        Request.client_ip4.in_(types.IPNetwork('1.2.3.4/32')),
        Request.method == 'GET',
        or_(
            not_(Request.path.match('/something/.+')),
            Request.query.contains('a'),
        )
    )

    def _visit(v):
        vs.append(v)
        return v

    vs = []
    e.traverse(bool_op=_visit, field_op=_visit, order=e.PREFIX)
    assert map(str, vs) == [
        'client_ip4 in 1.2.3.4/32 and method = "GET" and path !~ "/something/.+" or a in query',
        'client_ip4 in 1.2.3.4/32 and method = "GET"',
        'client_ip4 in 1.2.3.4/32',
        'method = "GET"',
        'path !~ "/something/.+" or a in query',
        'path !~ "/something/.+"',
        'a in query',
    ]

    vs = []
    e.traverse(bool_op=_visit, field_op=_visit, order=e.INFIX)
    assert map(str, vs) == [
        'client_ip4 in 1.2.3.4/32',
        'client_ip4 in 1.2.3.4/32 and method = "GET"',
        'method = "GET"',
        'client_ip4 in 1.2.3.4/32 and method = "GET" and path !~ "/something/.+" or a in query',
        'path !~ "/something/.+"',
        'path !~ "/something/.+" or a in query',
        'a in query',
    ]

    vs = []
    e.traverse(bool_op=_visit, field_op=_visit, order=e.POSTFIX)
    assert map(str, vs) == [
        'client_ip4 in 1.2.3.4/32',
        'method = "GET"',
        'client_ip4 in 1.2.3.4/32 and method = "GET"',
        'path !~ "/something/.+"',
        'a in query',
        'path !~ "/something/.+" or a in query',
        'client_ip4 in 1.2.3.4/32 and method = "GET" and path !~ "/something/.+" or a in query'
    ]
