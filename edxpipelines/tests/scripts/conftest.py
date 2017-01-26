import io

import os.path
import pytest
import yaml
from xml.etree import ElementTree

from edxpipelines.deploy import ensure_pipeline
from edxpipelines.canonicalize import canonicalize_gocd, PARSER


def pytest_addoption(parser):
    """
    Add options to py.test
    """
    group = parser.getgroup("GoCD", "GoCD tests", "general")
    group.addoption(
        "--config-file", default='config.yml',
        help="The config file to tests"
    )


def pytest_generate_tests(metafunc):
    """
    Generate test instances for all repositories to be checked.
    """

    if 'script' in metafunc.fixturenames:
        config_file = metafunc.config.rootdir.join(metafunc.config.option.config_file)

        with config_file.open() as config_file_stream:
            config_data = yaml.safe_load(config_file_stream)

        script_configs = [
            script
            for environment, scripts in config_data.items()
            for script in scripts
            if environment != 'anchors' and script.pop('enabled')
        ]

        metafunc.parametrize(
            'script',
            script_configs,
            ids=[script.get('script') for script in script_configs],
            scope='module'
        )


@pytest.fixture(scope='module')
def script_result(script):
    print script
    script_name = script.pop('script')
    os.environ['SAVE_CONFIG'] = "true"

    ensure_pipeline(
        script_name,
        dry_run=True,
        **script
    )
    input_tree = ElementTree.parse('config-after.xml', parser=PARSER)
    return canonicalize_gocd(input_tree)
