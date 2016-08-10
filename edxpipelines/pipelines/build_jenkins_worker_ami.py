#!/usr/bin/env python
import sys
from os import path
import click
from gomatic import *

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

import edxpipelines.utils as utils
import edxpipelines.patterns.stages as stages
import edxpipelines.constants as constants


@click.command()
@click.option(
    '--save-config', 'save_config_locally',
    envvar='SAVE_CONFIG',
    help='Save the pipeline configuration xml locally.',
    required=False,
    default=False
)
@click.option(
    '--dry-run',
    envvar='DRY_RUN',
    help='Perform a dry run of the pipeline installation, and save the pre/post xml configurations locally.',
    required=False,
    default=False,
    is_flag=True,
)
@click.option(
    '--variable_file', 'variable_files',
    multiple=True,
    help='Path to yaml variable file with a dictionary of key/value pairs to be used as variables in the script.',
    required=False,
    default=[]
)
@click.option(
    '-e', '--variable', 'cmd_line_vars',
    multiple=True,
    help='Key/value used as a replacement variable in this script, as in KEY=VALUE.',
    required=False,
    type=(str, str),
    nargs=2,
    default={}
)
def install_pipeline(save_config_locally, dry_run, variable_files, cmd_line_vars):
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

    Still need to sort out these things:
    "ami_name": "jenkins_worker-{{isotime | clean_ami_name}}",
    "ssh_username": "ubuntu",
    "ami_description": "jenkins worker",
    "tags": {
      "delete_or_keep": "{{user `delete_or_keep`}}"
    }
    """
    config = utils.merge_files_and_dicts(variable_files, list(cmd_line_vars,))

    gcc = GoCdConfigurator(HostRestClient(config['gocd_url'], config['gocd_username'], config['gocd_password'], ssl=True))
    pipeline = gcc.ensure_pipeline_group('Jenkins').ensure_replacement_of_pipeline('build-jenkins-workers')
    pipeline.ensure_material(GitMaterial(
        'https://github.com/edx/tubular',
        material_name='tubular',
        polling=False,
        destination_directory='tubular'
    ))
    pipeline.ensure_material(GitMaterial(
        'https://github.com/edx/configuration',
        branch='master',
        material_name='configuration',
        polling=False,
        destination_directory='configuration',
    ))

    #
    # Create the AMI-building stage.
    #
    stages.generate_launch_instance(
        pipeline,
        config['aws_access_key_id'],
        config['aws_secret_access_key'],
        config['ec2_vpc_subnet_id'],
        config['ec2_security_group_id'],
        config['ec2_instance_profile_name'],
        config['base_ami_id'],
        ec2_instance_type='m3.large',
    )

    stages.generate_run_play(
        pipeline,
        '../edx-east/jenkins_worker.yml',
        play='jenkins_worker',
        deployment='edx',
        edx_environment='loadtest',
        private_github_key=config['github_private_key'],
        app_repo=None,
        configuration_secure_repo=config['configuration_secure_repo'],
        configuration_repo='https://github.com/edx/configuration.git',
        hipchat_auth_token=config['hipchat_token'],
        hipchat_room='testeng',
    )

    stages.generate_create_ami_from_instance(
        pipeline,
        play='programs',
        deployment='edx',
        edx_environment='loadtest',
        app_repo=None,
        configuration_secure_repo=config['configuration_secure_repo'],
        configuration_repo='https://github.com/edx/configuration.git',
        hipchat_auth_token=config['hipchat_token'],
        hipchat_room='release pipeline',
        aws_access_key_id=config['aws_access_key_id'],
        aws_secret_access_key=config['aws_secret_access_key'],
    )
    #
    # Create the stage to terminate the EC2 instance used to build the AMI.
    #
    instance_info_location = utils.ArtifactLocation(
        pipeline.name,
        constants.LAUNCH_INSTANCE_STAGE_NAME,
        constants.LAUNCH_INSTANCE_JOB_NAME,
        'launch_info.yml'
    )
    stages.generate_terminate_instance(
        pipeline,
        instance_info_location,
        aws_access_key_id=config['aws_access_key_id'],
        aws_secret_access_key=config['aws_secret_access_key'],
        hipchat_auth_token=config['hipchat_token'],
        runif='any'
    )

    gcc.save_updated_config(save_config_locally=save_config_locally, dry_run=dry_run)

if __name__ == "__main__":
    install_pipeline()
