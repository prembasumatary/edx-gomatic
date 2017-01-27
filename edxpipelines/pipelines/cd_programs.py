#!/usr/bin/env python
import sys
from os import path

import click

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

from edxpipelines import utils
from edxpipelines.patterns import pipelines
from edxpipelines.pipelines.script import pipeline_script


@pipeline_script()
def install_pipeline(configurator, config, env_configs):
    """
    Variables needed for this pipeline:
    - gocd_username
    - gocd_password
    - gocd_url
    - configuration_secure_repo
    - configuration_internal_repo
    - hipchat_token
    - github_private_key
    - aws_access_key_id
    - aws_secret_access_key
    - ec2_vpc_subnet_id
    - ec2_security_group_id
    - ec2_instance_profile_name
    - base_ami_id
    """
    version_env_var = '$GO_REVISION_PROGRAMS'
    pipelines.generate_basic_multistage_pipeline(
        configurator,
        play='programs',
        pipeline_group='E-Commerce',
        playbook_path='playbooks/edx-east/programs.yml',
        app_repo='https://github.com/edx/programs.git',
        service_name='programs',
        hipchat_room='release',
        config=config,
        app_version=version_env_var,
        PROGRAMS_VERSION=version_env_var
    )


if __name__ == "__main__":
    install_pipeline()
