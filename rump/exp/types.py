"""
"""
import pilo
import netaddr


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


#:
int = int


#:
str = str


#:
bool = bool


#:
NamedTuple = pilo.Form


#:
IPAddress = netaddr.IPAddress


#:
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
    """

    pass


class HeaderHash(StringHash):
    """
    """

    pass


class ArgumentHash(StringHash):
    """
    """

    pass
