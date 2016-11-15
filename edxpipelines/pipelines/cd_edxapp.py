#!/usr/bin/env python
import sys
from os import path
import click
from gomatic import *

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

import edxpipelines.utils as utils
import edxpipelines.patterns.stages as stages
import edxpipelines.patterns.pipelines as pipelines
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
    '--bmd-steps',
    envvar='BMD_STEPS',
    help='Specify which steps to perform of build, migrate, deploy by specifying some subset of the letters "bmd".',
    required=False,
    default='bmd'
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
def install_pipelines(save_config_locally, dry_run, bmd_steps, variable_files, cmd_line_vars):
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

    Optional variables:
    - configuration_secure_version
    - configuration_internal_version
    """
    BMD_STAGES = {
        'b': generate_build_stages,
        'm': generate_migrate_stages,
        'd': generate_deploy_stages
    }

    # Sort the BMD steps by the custom 'bmd' alphabet
    bmd_steps = sort_bmd(bmd_steps.lower())

    # validate the caller has requested a valid pipeline configuration
    validate_pipeline_permutations(bmd_steps)

    # Merge the configuration files/variables together
    config = utils.merge_files_and_dicts(variable_files, list(cmd_line_vars,))

    # Create the pipeline
    gcc = GoCdConfigurator(HostRestClient(config['gocd_url'], config['gocd_username'], config['gocd_password'], ssl=True))
    pipeline_group = config['pipeline_group']

    # Some pipelines will need to know the name of the upstream pipeline that built the AMI.
    # Determine the build pipeline name and add it to the config.
    pipeline_name, pipeline_name_build = determine_pipeline_names(config, bmd_steps)
    if 'pipeline_name_build' in config:
        raise Exception("The config 'pipeline_name_build' value exists but should only be programmatically generated!")
    config['pipeline_name_build'] = pipeline_name_build

    pipeline = gcc.ensure_pipeline_group(pipeline_group)\
                  .ensure_replacement_of_pipeline(pipeline_name)

    # Setup the materials
    # Example materials yaml
    # materials:
    #   - url: "https://github.com/edx/tubular"
    #     branch: "master"
    #     material_name: "tubular"
    #     polling: "True"
    #     destination_directory: "tubular"
    #     ignore_patterns:
    #     - '**/*'
    for material in config.get('materials', []):
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

    # Setup the upstream pipeline materials
    for material in config.get('upstream_pipelines', []):
        pipeline.ensure_material(
            PipelineMaterial(
                pipeline_name=material['pipeline_name'],
                stage_name=material['stage_name'],
                material_name=material['material_name']
            )
        )

    # We always need to launch the AMI, independent deploys are done with a different pipeline
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

    # Generate all the requested stages
    for phase in bmd_steps:
        BMD_STAGES[phase](pipeline, config)

    # Add the cleanup stage
    generate_cleanup_stages(pipeline, config)

    gcc.save_updated_config(save_config_locally=save_config_locally, dry_run=dry_run)


def generate_build_stages(pipeline, config):
    stages.generate_run_play(
        pipeline,
        'playbooks/edx-east/edxapp.yml',
        play=config['play_name'],
        deployment=config['edx_deployment'],
        edx_environment=config['edx_environment'],
        private_github_key=config['github_private_key'],
        app_repo=config['app_repo'],
        configuration_secure_dir='{}-secure'.format(config['edx_deployment']),
        configuration_internal_dir='{}-internal'.format(config['edx_deployment']),
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
        configuration_internal_repo=config['{}_configuration_internal_repo'.format(config['edx_deployment'])],
        configuration_repo=config['configuration_url'],
        hipchat_auth_token=config['hipchat_token'],
        hipchat_room='release pipeline',
        configuration_version='$GO_REVISION_CONFIGURATION',
        configuration_secure_version='$GO_REVISION_{}_SECURE'.format(config['edx_deployment'].upper()),
        configuration_internal_version='$GO_REVISION_{}_SECURE'.format(config['edx_deployment'].upper()),
        aws_access_key_id=config['aws_access_key_id'],
        aws_secret_access_key=config['aws_secret_access_key'],
        edxapp_theme_source_repo=config['theme_url'],
        edxapp_theme_version='$GO_REVISION_EDX_MICROSITE',
    )

    return pipeline


def generate_migrate_stages(pipeline, config):
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
        constants.LAUNCH_INSTANCE_FILENAME
    )
    for sub_app in config['edxapp_subapps']:
        stages.generate_run_migrations(
            pipeline,
            db_migration_pass=config['db_migration_pass'],
            inventory_location=ansible_inventory_location,
            instance_key_location=instance_ssh_key_location,
            launch_info_location=launch_info_location,
            application_user=config['db_migration_user'],
            application_name=config['play_name'],
            application_path=config['application_path'],
            sub_application_name=sub_app
        )

    return pipeline


def generate_deploy_stages(pipeline, config):
    #
    # Create the stage to deploy the AMI.
    #
    ami_file_location = utils.ArtifactLocation(
        config['pipeline_name_build'],
        constants.BUILD_AMI_STAGE_NAME,
        constants.BUILD_AMI_JOB_NAME,
        constants.BUILD_AMI_FILENAME
    )
    stages.generate_deploy_ami(
        pipeline,
        config['asgard_api_endpoints'],
        config['asgard_token'],
        config['aws_access_key_id'],
        config['aws_secret_access_key'],
        ami_file_location,
        manual_approval=not config.get('auto_deploy_ami', False)
    )
    return pipeline


def generate_cleanup_stages(pipeline, config):
    #
    # Create the stage to terminate the EC2 instance used to both build the AMI and run DB migrations.
    #
    instance_info_location = utils.ArtifactLocation(
        config['pipeline_name_build'],
        constants.LAUNCH_INSTANCE_STAGE_NAME,
        constants.LAUNCH_INSTANCE_JOB_NAME,
        constants.LAUNCH_INSTANCE_FILENAME
    )
    stages.generate_terminate_instance(
        pipeline,
        instance_info_location,
        aws_access_key_id=config['aws_access_key_id'],
        aws_secret_access_key=config['aws_secret_access_key'],
        hipchat_auth_token=config['hipchat_token'],
        runif='any'
    )
    return pipeline


# key is what is passed in
# value is the suffix used for the pipeline name
valid_permutations = {
    'bmd': 'B-M-D',
    'md': 'M-D',
    'b': 'B'
}

def sort_bmd(bmd_steps):
    alphabet = 'bmd'
    try:
        return ''.join(sorted(bmd_steps, key=lambda pipeline_stage: alphabet.index(pipeline_stage)))
    except ValueError:
        raise Exception('only valid stages are b, m, d and must be one of {}'.format(valid_permutations.keys()))

def validate_pipeline_permutations(bmd_steps):
    try:
        valid_permutations[bmd_steps.lower()]
    except KeyError:
        raise Exception('Only supports total Build/Migrate/Deploy, Build-only, and Migrate/Deploy-only pipelines.')

def determine_pipeline_names(config, bmd_steps):
    """
    Depending on whether the BMD steps of the pipeline, read/return the correct pipeline_name config vars.
    """
    def _generate_pipeline_name(config, bmd_steps):
        return '{pipeline_name}_{suffix}'\
            .format(pipeline_name=config['pipeline_name'], suffix=valid_permutations[bmd_steps])

    pipeline_name = _generate_pipeline_name(config, bmd_steps)
    pipeline_name_build = _generate_pipeline_name(config, 'b')
    if bmd_steps == 'bmd':
        pipeline_name_build = pipeline_name
    return pipeline_name, pipeline_name_build

if __name__ == "__main__":
    install_pipelines()
