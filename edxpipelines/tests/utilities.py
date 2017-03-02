"""
Utility classes and functions for writing tests of edxpipelines.
"""
from collections import defaultdict
import itertools


class ContextSet(object):
    """
    A set-like object that keeps track of what contexts the elements of the set
    were found in.
    """
    # pylint: disable=protected-access

    def __init__(self, name, contexts=()):
        self.name = name

        # A dict mapping from values to the contexts they came from
        self._contexts = defaultdict(list)

        for item, context in contexts:
            self.add(item, context)

    def add(self, item, context):
        """
        Add ``item`` to the ContextSet, recording it as having come from ``context``.
        """
        self._contexts[item].append(context)

    def iteritems(self):
        """
        Yield all (item, context) pairs that have been added to this ContextSet.
        """
        for item, contexts in self._contexts.iteritems():
            for context in contexts:
                yield item, context

    def __lt__(self, other):
        if isinstance(other, (set, frozenset)):
            return set(self._contexts) < other

        if not isinstance(other, ContextSet):
            return NotImplemented

        return set(self._contexts) < set(other._contexts)

    def __le__(self, other):
        if isinstance(other, (set, frozenset)):
            return set(self._contexts) <= other

        if not isinstance(other, ContextSet):
            return NotImplemented

        return set(self._contexts) <= set(other._contexts)

    def __eq__(self, other):
        if isinstance(other, (set, frozenset)):
            return set(self._contexts) == other

        if not isinstance(other, ContextSet):
            return NotImplemented

        return set(self._contexts) == set(other._contexts)

    def __ne__(self, other):
        if isinstance(other, (set, frozenset)):
            return set(self._contexts) != other

        if not isinstance(other, ContextSet):
            return NotImplemented

        return set(self._contexts) != set(other._contexts)

    def __and__(self, other):
        if not isinstance(other, ContextSet):
            return NotImplemented

        return ContextSet(
            "{} & {}".format(self.name, other.name),
            (
                (item, context)
                for item in set(self._contexts) & set(other._contexts)
                for context in itertools.chain(
                    ("{} -> {}".format(self.name, context) for context in self._contexts[item]),
                    ("{} -> {}".format(other.name, context) for context in other._contexts[item])
                )
            )
        )

    def __repr__(self):
        return "ContextSet({!r}, {!r})".format(self.name, list(self.iteritems()))
