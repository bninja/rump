import collections
import random


class Server(collections.namedtuple('Server', ['protocol', 'location'])):
    """
    An upstream server represented as a

    - protocol (e.g. 'http')
    - location (e.g. '127.0.0.1:5001')

    string, string pair.
    """

    default_protcol = 'http'


class Selection(collections.namedtuple('Selection', ['server', 'weight'])):
    """
    An upstream selection as a:

    - server (e.g. Server('http', '127.0.0.1:5115'))
    - weight (e.g. 12)

    string, integer pair.
    """

    pass


class Upstream(collections.MutableSequence):
    """
    A collection of upstream server selections.
    """

    def __init__(self, *selections):
        if len(selections) == 1:
            if isinstance(selections[0], list):
                selections = selections[0]
            elif isinstance(selections[0], Upstream):
                selections = selections[0]
        selections = [
            v if isinstance(v, Selection) else Selection(v) for v in selections
        ]
        self.selections = selections
        self.total = sum(selection.weight for selection in self)
        self.uniform = len(set(selection.weight for selection in self)) == 1

    @property
    def servers(self):
        return [selection.server for selection in self]

    def __call__(self):
        if self.uniform:
            return random.choice(self).server
        offset, choice = 0, random.randint(0, self.total - 1)
        for selection in self:
            if choice < offset + selection.weight:
                return selection.server
            offset += selection.weight
        raise Exception('{0} has no upstream for choice {1}', self, choice)

    def __str__(self):
        return ' '.join([
            '{protocol}://{location},{weight}'.format(
                protocol=selection.server.protocol,
                location=selection.server.location,
                weight=selection.weight,
            )
            for selection in self
        ])

    def __eq__(self, other):
        return self.selections == other

    def __neq__(self, other):
        return not self.__eq__(other)

    # collections.MutableSequence

    def __getitem__(self, index):
        return self.selections[index]

    def __len__(self):
        return len(self.selections)

    def __setitem__(self, index, value):
        self.selections[index] = value

    def __delitem__(self, index):
        del self.selections[index]

    def insert(self, index, value):
        self.selections.insert(index, value)
