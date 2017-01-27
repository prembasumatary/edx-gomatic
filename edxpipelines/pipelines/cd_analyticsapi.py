#!/usr/bin/env python
import sys
from os import path
import click
from gomatic import *

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

from edxpipelines import utils
from edxpipelines.patterns import pipelines
from edxpipelines import constants
from edxpipelines.pipelines.script import pipeline_script


def install_pipelines(configurator, config, env_configs):
    """
    Variables needed for this pipeline:
    - gocd_username
    - gocd_password
    - gocd_url
    - configuration_secure_repo
    - hipchat_token
    - github_private_key
    - aws_access_key_id
    - aws_secret_access_key
    - ec2_vpc_subnet_id
    - ec2_security_group_id
    - ec2_instance_profile_name
    - base_ami_id
    """

    analytics_api_env_var = '$GO_REVISION_ANALYTICSAPI'
    pipelines.generate_basic_multistage_pipeline(
        configurator,
        play='analyticsapi',
        playbook_path='playbooks/edx-east/analyticsapi.yml',
        app_repo='https://github.com/edx/edx-analytics-data-api.git',
        service_name='analytics_api',
        hipchat_room='Analytics',
        pipeline_group='Analytics',
        config=config,
        app_version=analytics_api_env_var,
        ANALYTICS_API_VERSION=analytics_api_env_var
    )


if __name__ == "__main__":
    pipeline_script(install_pipelines)
