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

    Optional variables:
    - configuration_secure_version
    """
    config = utils.merge_files_and_dicts(variable_files, list(cmd_line_vars,))

    gcc = GoCdConfigurator(HostRestClient(config['gocd_url'], config['gocd_username'], config['gocd_password'], ssl=True))
    pipeline = gcc.ensure_pipeline_group(config['pipeline_group'])\
                  .ensure_replacement_of_pipeline(config['pipeline_name'])

    # Example materials yaml
    # materials:
    #   - url: "https://github.com/edx/tubular"
    #     branch: "master"
    #     material_name: "tubular"
    #     polling: "True"
    #     destination_directory: "tubular"
    #     ignore_patterns:
    #     - '**/*'

    for material in config['materials']:
        pipeline.ensure_material(
            GitMaterial(
                url=material['url'],
                branch=material['branch'],
                material_name=material['material_name'],
                polling=material['polling'],
                destination_directory=material['destination_directory'],
                ignore_patterns=material['ignore_patterns']
            )
        )

    # If no upstream pipelines exist, don't install them!
    for material in config.get('upstream_piplines', []):
        pipeline.ensure_material(
            PipelineMaterial(
                pipeline_name=material['pipeline_name'],
                stage_name=material['stage_name'],
                material_name=material['material_name']
            )
        )

    #
    # Create the AMI-building stage.
    #
    launch_stage = stages.generate_launch_instance(
        pipeline,
        config['aws_access_key_id'],
        config['aws_secret_access_key'],
        config['ec2_vpc_subnet_id'],
        config['ec2_security_group_id'],
        config['ec2_instance_profile_name'],
        config['base_ami_id'],
        manual_approval=not config.get('auto_run', False)
    )

    stages.generate_run_play(
        pipeline,
        'playbooks/edx-east/edxapp.yml',
        play=config['play_name'],
        deployment=config['edx_deployment'],
        edx_environment=config['edx_environment'],
        private_github_key=config['github_private_key'],
        app_repo=config['app_repo'],
        configuration_secure_dir='{}-secure'.format(config['edx_deployment']),
        hipchat_token=config['hipchat_token'],
        hipchat_room='release',
        edx_platform_version='$GO_REVISION_EDX_PLATFORM',
        edx_platform_repo='$APP_REPO',
        configuration_version='$GO_REVISION_CONFIGURATION',
        edxapp_theme_source_repo=config['theme_url'],
        edxapp_theme_version='$GO_REVISION_EDX_THEME',
        edxapp_theme_name='$EDXAPP_THEME_NAME',
        disable_edx_services='true',
        COMMON_TAG_EC2_INSTANCE='true',
        cache_id='$GO_PIPELINE_COUNTER'
    )

    stages.generate_create_ami_from_instance(
        pipeline,
        play=config['play_name'],
        deployment=config['edx_deployment'],
        edx_environment=config['edx_environment'],
        app_repo=config['app_repo'],
        app_version='$GO_REVISION_EDX_PLATFORM',
        configuration_secure_repo=config['{}_configuration_secure_repo'.format(config['edx_deployment'])],
        configuration_repo=config['configuration_url'],
        hipchat_auth_token=config['hipchat_token'],
        hipchat_room='release pipeline',
        configuration_version='$GO_REVISION_CONFIGURATION',
        configuration_secure_version='$GO_REVISION_{}_SECURE'.format(config['edx_deployment'].upper()),
        aws_access_key_id=config['aws_access_key_id'],
        aws_secret_access_key=config['aws_secret_access_key'],
        edxapp_theme_source_repo=config['theme_url'],
        edxapp_theme_version='$GO_REVISION_EDX_MICROSITE',
    )

    #
    # Create the DB migration running stage.
    #
    ansible_inventory_location = utils.ArtifactLocation(
        pipeline.name,
        constants.LAUNCH_INSTANCE_STAGE_NAME,
        constants.LAUNCH_INSTANCE_JOB_NAME,
        'ansible_inventory'
    )
    instance_ssh_key_location = utils.ArtifactLocation(
        pipeline.name,
        constants.LAUNCH_INSTANCE_STAGE_NAME,
        constants.LAUNCH_INSTANCE_JOB_NAME,
        'key.pem'
    )
    launch_info_location = utils.ArtifactLocation(
        pipeline.name,
        constants.LAUNCH_INSTANCE_STAGE_NAME,
        constants.LAUNCH_INSTANCE_JOB_NAME,
        'launch_info.yml'
    )
    for sub_app in config['edxapp_subapps']:
        stages.generate_run_migrations(
            pipeline,
            db_migration_pass=config['db_migration_pass'],
            inventory_location=ansible_inventory_location,
            instance_key_location=instance_ssh_key_location,
            launch_info_location=launch_info_location,
            application_user=config['play_name'],
            application_name=config['play_name'],
            application_path=config['application_path'],
            sub_application_name=sub_app
        )

    #
    # Create the stage to deploy the AMI.
    #
    ami_file_location = utils.ArtifactLocation(
        pipeline.name,
        constants.BUILD_AMI_STAGE_NAME,
        constants.BUILD_AMI_JOB_NAME,
        'ami.yml'
    )
    stages.generate_basic_deploy_ami(
        pipeline,
        config['asgard_api_endpoints'],
        config['asgard_token'],
        config['aws_access_key_id'],
        config['aws_secret_access_key'],
        ami_file_location,
        manual_approval=not config.get('auto_deploy_ami', False)
    )

    #
    # Create the stage to terminate the EC2 instance used to both build the AMI and run DB migrations.
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
