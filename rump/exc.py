import pilo
import pyparsing


__all__ = [
    'ParseException',
    'InvalidField',
    'MissingField',
    'RouterNotDynamic',
    'RouterNotConneted',
]


ParseException = pyparsing.ParseException

InvalidField = pilo.Invalid

MissingField = pilo.Missing


class RouterNotDynamic(Exception):

    def __init__(self, router):
        super(RouterNotDynamic, self).__init__()


class RouterNotConnected(Exception):

    def __init__(self, router):
        super(RouterNotConnected, self).__init__()
