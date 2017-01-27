#!/usr/bin/env python
import sys
from os import path
import click
from gomatic import *

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

from edxpipelines import utils
from edxpipelines.patterns import stages
from edxpipelines.patterns import tasks
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
    artifact_path = 'target/'

    pipeline = configurator.ensure_pipeline_group(
        config['pipeline_group']
    ).ensure_replacement_of_pipeline(
        config['pipeline_name']
    ).ensure_material(
        GitMaterial(
            'https://github.com/edx/edx-gomatic',
            material_name='edx-gomatic',
            polling=True,
            destination_directory='edx-gomatic',
            branch='master'
        )
    ).ensure_material(
        GitMaterial(
            'git@github.com:edx-ops/gomatic-secure.git',
            material_name='gomatic-secure',
            polling=True,
            destination_directory='gomatic-secure',
            branch='master',
            ignore_patterns=constants.MATERIAL_IGNORE_ALL_REGEX
        )
    )

    pipeline.ensure_encrypted_environment_variables(
        {
            'GOMATIC_USER': config['gomatic_user'],
            'GOMATIC_PASSWORD': config['gomatic_password']
        }
    )

    stage = pipeline.ensure_stage('deploy_gomatic_stage')
    job = stage.ensure_job('deploy_gomatic_scripts_job')
    tasks.generate_requirements_install(job, 'edx-gomatic')

    job.add_task(
        ExecTask(
            [
                '/usr/bin/python',
                './deploy_pipelines.py',
                '-v',
                'tools',
                '-f',
                'config.yml'
            ],
            working_dir='edx-gomatic'
        )
    )


if __name__ == '__main__':
    pipeline_script(install_pipelines)
