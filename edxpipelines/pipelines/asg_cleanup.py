#!/usr/bin/env python
import sys
import click
from os import path
from gomatic import *

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

from edxpipelines import utils
from edxpipelines import constants
from edxpipelines.patterns import stages
from edxpipelines.pipelines.script import pipeline_script


def install_pipelines(configurator, config, env_configs):
    """
    Variables needed for this pipeline:
    - gocd_username
    - gocd_password
    - gocd_url
    - pipeline_group
    - pipeline_name
    - asgard_api_endpoints
    - asgard_token
    - aws_access_key_id
    - aws_secret_access_key
    - cron_timer
    """

    pipeline = configurator.ensure_pipeline_group(config['pipeline_group'])\
                           .ensure_replacement_of_pipeline(config['pipeline_name'])\
                           .set_timer(config['cron_timer'])\
                           .set_git_material(GitMaterial("https://github.com/edx/tubular.git",
                                                         polling=True,
                                                         destination_directory="tubular",
                                                         ignore_patterns=constants.MATERIAL_IGNORE_ALL_REGEX
                                                         )
                                             )

    stages.generate_asg_cleanup(pipeline, config['asgard_api_endpoints'], config['asgard_token'], config['aws_access_key_id'], config['aws_secret_access_key'])

if __name__ == "__main__":
    pipeline_script(install_pipelines)