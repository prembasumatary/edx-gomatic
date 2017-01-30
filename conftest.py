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