"""
Pytest fixtures for tests running against GoCD XML output.
"""

import imp
from xml.etree import ElementTree

import pytest
import yaml

from gomatic import GoCdConfigurator, empty_config
from edxpipelines.deploy import ensure_pipeline
from edxpipelines.canonicalize import canonicalize_gocd, PARSER
from edxpipelines.utils import EDP


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


class TestConfigMerger(object):
    """
    A ConfigMerger that returns a dummy string for any missing keys.
    """
    def __init__(self, test_config):
        self.test_config = test_config

    def __getitem__(self, key):
        if isinstance(key, basestring):
            return self[None].get(key, 'dummy_{}'.format(key))

        if key is None:
            return self.test_config['global-config']

        actual_config = MirrorDict()
        actual_config.update(self.test_config['global-config'])
        for i in (-2, -1, 0):
            actual_config.update(self.test_config.get('-'.join(val for val in key[:i] if val), {}))
        return actual_config

    def get(self, key, default=None):
        """
        Return the config value for key, unless it doesn't exist, in which case return default.
        """
        try:
            return self[key]
        except KeyError:
            return default

    def by_environments(self):
        """
        Yield all per-environment configs stored in this TestConfigMerger.
        """
        envs = set(key.split('-')[0] for key in self.test_config if key != 'global-config')
        for env in envs:
            yield self[EDP(env)]


def dummy_ensure_pipeline(script):
    """
    Run ``script`` against a dummy GoCdConfigurator set to
    export the config-after.xml.
    """
    configurator = GoCdConfigurator(empty_config())

    with open('test-config.yml') as test_config_file:
        test_config = yaml.safe_load(test_config_file)

    config = TestConfigMerger(test_config)

    script = imp.load_source('pipeline_script', script)
    script.install_pipelines(configurator, config)
    configurator.save_updated_config(save_config_locally=True, dry_run=True)


@pytest.fixture(scope='module')
def script_result(script, pytestconfig):
    """
    A pytest fixture that loads executes a script (either against a live server
    or a dummy server), and returns the parsed results in canonical format.
    """
    script_path = script.get('script')

    if pytestconfig.getoption('live'):
        ensure_pipeline(
            dry_run=True,
            save_config_locally=True,
            **script
        )
    else:
        dummy_ensure_pipeline(script_path)

    input_tree = ElementTree.parse('config-after.xml', parser=PARSER)
    return canonicalize_gocd(input_tree)


@pytest.fixture(scope='module')
def script_name(script):
    """
    A pytest fixture that returns the name of the supplied script.
    """
    return script.get('script')
