"""
Module to add configuration used by various tests.
"""


def pytest_addoption(parser):
    """
    Add options to py.test
    """
    group = parser.getgroup("GoCD", "GoCD tests", "general")
    group.addoption(
        "--config-file", default='config.yml',
        help="The config file to tests"
    )
    group.addoption(
        "--live", action='store_true',
        help="Whether to run the consistency tests against a live server"
    )


def pytest_assertrepr_compare(op, left, right):  # pylint: disable=invalid-name
    """
    Format assertions around set equality/emptiness.
    """
    if isinstance(left, (set, frozenset)) and isinstance(right, (set, frozenset)):
        if op == '<=':
            return [
                '{left.__class__.__name__}(...) {op} {right.__class__.__name__}(...):'.format(
                    left=left, op=op, right=right
                ),
                'Items missing from the righthand set:'
            ] + [
                '    {!r}'.format(item)
                for item in left - right
            ]
        elif op == '==' and not right:
            return [
                '{left.__class__.__name__}(...) is not empty'.format(left=left),
                'Unexpected items in the lefthand set:',
            ] + [
                '    {!r}'.format(item)
                for item in left
            ]
