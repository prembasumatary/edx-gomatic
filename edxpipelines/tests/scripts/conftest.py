from collections import defaultdict
import io
import imp

import os.path
import pytest
import yaml
from xml.etree import ElementTree

from gomatic import GoCdConfigurator, empty_config
from edxpipelines.deploy import ensure_pipeline
from edxpipelines.canonicalize import canonicalize_gocd, PARSER


def pytest_generate_tests(metafunc):
    """
    Generate test instances for all scripts to be checked.
    """

    if 'script' in metafunc.fixturenames:
        config_file = metafunc.config.rootdir.join(metafunc.config.option.config_file)

        with config_file.open() as config_file_stream:
            config_data = yaml.safe_load(config_file_stream)

        # Read all of the scripts from the specified config.yml file.
        script_configs = [
            script
            for environment, scripts in config_data.items()
            for script in scripts
            if environment != 'anchors' and script.pop('enabled')
        ]

        # Inject those scripts via the `script` argument to tests and fixtures
        metafunc.parametrize(
            'script',
            script_configs,
            ids=lambda script: script.get('script'),
            scope='module'
        )


class MirrorDict(dict):
    """
    A dict that returns a dummy string for any missing keys.
    """
    def __missing__(self, key):
        return "dummy_{}".format(key)


def dummy_ensure_pipeline(script_name):
    """
    Run ``script_name`` against a dummy GoCdConfigurator set to
    export the config-after.xml.
    """
    configurator = GoCdConfigurator(empty_config())

    env_configs = defaultdict(MirrorDict)
    config = MirrorDict()

    with open('test-config.yml') as test_config_file:
        test_config = yaml.safe_load(test_config_file)

    if 'global-config' in test_config:
        config.update(test_config.pop('global-config'))

    for env, values in test_config.items():
        env_configs[env].update(values)

    script = imp.load_source('pipeline_script', script_name)
    script.install_pipelines(configurator, config, env_configs)
    configurator.save_updated_config(save_config_locally=True, dry_run=True)


@pytest.fixture(scope='module')
def script_result(script, pytestconfig):
    """
    A pytest fixture that loads executes a script (either against a live server
    or a dummy server), and returns the parsed results in canonical format.
    """
    script_name = script.get('script')

    if pytestconfig.getoption('live'):
        ensure_pipeline(
            dry_run=True,
            save_config_locally=True,
            **script
        )
    else:
        dummy_ensure_pipeline(script_name)

    input_tree = ElementTree.parse('config-after.xml', parser=PARSER)
    return canonicalize_gocd(input_tree)


@pytest.fixture(scope='module')
def script_name(script):
    """
    A pytest fixture that returns the name of the supplied script.
    """
    return script.get('script')
