#!/usr/bin/env python
import sys
from os import path

import click

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

import edxpipelines.utils as utils
from edxpipelines.patterns import pipelines


@click.command()
@click.option(
    '--save-config', 'save_config_locally',
    envvar='SAVE_CONFIG',
    help='Save the pipeline configuration xml locally.',
    required=False,
    default=False,
    is_flag=True
)
@click.option(
    '--dry-run',
    envvar='DRY_RUN',
    help='Perform a dry run of the pipeline installation, and save the pre/post xml configurations locally.',
    required=False,
    default=False,
    is_flag=True
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
    """
    config = utils.merge_files_and_dicts(variable_files, list(cmd_line_vars, ))

    version_env_var = '$GO_REVISION_ECOMMERCE'
    pipelines.generate_basic_multistage_pipeline(
        play='ecommerce',
        pipeline_group='E-Commerce',
        playbook_path='playbooks/edx-east/ecommerce.yml',
        app_repo='https://github.com/edx/ecommerce.git',
        service_name='ecommerce',
        hipchat_room='release',
        config=config,
        save_config_locally=save_config_locally,
        dry_run=dry_run,
        app_version=version_env_var,
        ECOMMERCE_VERSION=version_env_var
    )


if __name__ == "__main__":
    install_pipeline()
