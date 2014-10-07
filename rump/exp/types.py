"""
All types supported by:

- matching expressions (see `rump.exp`) and
- computed by request fields (see ``rump.request``)

"""
import netaddr
import pilo


__all__ = [
    'int',
    'str',
    'bool',
    'NamedTuple',
    'IPAddress',
    'IPNetwork',
    'StringHash',
    'HeaderHash',
    'ArgumentHash',
]

int = int

str = str

bool = bool

NamedTuple = pilo.Form

IPAddress = netaddr.IPAddress

IPNetwork = netaddr.IPNetwork


class Hash(dict):

    def __getattr__(self, key):
        try:
            return self.__getitem__(key)
        except KeyError:
            raise AttributeError(
                '"{0}" object has no attribute "{1}"'
                .format(type(self).__name__, key)
            )


class StringHash(Hash):
    """
    ``Hash`` specialization to have **string** keys.
    """

    pass


class HeaderHash(StringHash):
    """
    A specialization of a string hash expected to have **header** keys (e.g.
    insensitive to case).
    """

    pass


class ArgumentHash(StringHash):
    """
    A specialization of a string hash expected to have argument keys (e.g. for
    representing query strings, application/x-www-form-urlencoded content,
    etc).
    """

    pass
