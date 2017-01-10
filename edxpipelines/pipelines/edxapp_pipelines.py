#!/usr/bin/env python
from functools import partial
import sys
from os import path
from gomatic import *

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

import edxpipelines.utils as utils
import edxpipelines.patterns.stages as stages
import edxpipelines.patterns.pipelines as pipelines
import edxpipelines.constants as constants
from edxpipelines.materials import (
    TUBULAR, CONFIGURATION, EDX_PLATFORM, EDX_SECURE, EDGE_SECURE, MCKINSEY_SECURE,
    EDX_MICROSITE, EDX_INTERNAL, EDGE_INTERNAL, MCKINSEY_INTERNAL
)


def cut_branch(gcc, variable_files, cmd_line_vars):
    """
    Variables needed for this pipeline:
    - git_token
    """
    config = utils.merge_files_and_dicts(variable_files, list(cmd_line_vars,))

    pipeline = gcc.ensure_pipeline_group('edxapp')\
                  .ensure_replacement_of_pipeline('edxapp_cut_release_candidate')

    source_branch = 'master'

    pipeline.ensure_material(
        GitMaterial(
            url="https://github.com/edx/edx-platform",
            branch=source_branch,
            material_name='edx-platform',
            polling=True,
            destination_directory='edx-platform',
            ignore_patterns=['']
        )
    )
    pipeline.ensure_material(
        GitMaterial(
            url="https://github.com/edx/tubular",
            branch='master',
            material_name='tubular',
            polling='True',
            destination_directory='tubular',
            ignore_patterns=['**/*']
        )
    )

    stages.generate_create_branch(
        pipeline,
        constants.GIT_CREATE_BRANCH_STAGE_NAME,
        'edx',
        'edx-platform',
        source_branch,
        'release-candidate',
        config['git_token'],
        manual_approval=True,
    )
    pipeline.set_timer('0 0/5 15-19 ? * MON-FRI', True)

    return pipeline


def prerelease_materials(gcc, variable_files, cmd_line_vars):
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

    pipeline = gcc.ensure_pipeline_group('edxapp')\
                  .ensure_replacement_of_pipeline("prerelease_edxapp_materials_latest")

    for material in (
        TUBULAR, CONFIGURATION, EDX_SECURE, EDGE_SECURE, MCKINSEY_SECURE,
        EDX_MICROSITE, EDX_INTERNAL, EDGE_INTERNAL, MCKINSEY_INTERNAL
    ):
        pipeline.ensure_material(material)
    
    pipeline.ensure_material(
        GitMaterial(
            url=EDX_PLATFORM.url,
            branch=EDX_PLATFORM.branch,
            material_name=EDX_PLATFORM.material_name,
            polling=EDX_PLATFORM.polling,
            destination_directory=EDX_PLATFORM.destination_directory,
            ignore_patterns=[],
        )
    )

    # If no upstream pipelines exist, don't install them!
    for material in config.get('upstream_pipelines', []):
        pipeline.ensure_material(
            PipelineMaterial(
                pipeline_name=material['pipeline_name'],
                stage_name=material['stage_name'],
                material_name=material['material_name']
            )
        )

    # This stage only logs material information - but needed to be left in temporarily
    # as it used to be a stage that was an upstream material for three other pipelines.
    stages.generate_armed_stage(pipeline, constants.PRERELEASE_MATERIALS_STAGE_NAME)

    base_ami_id = ''
    if 'base_ami_id' in config:
        base_ami_id = config['base_ami_id']
    stages.generate_base_ami_selection(
        pipeline,
        config['aws_access_key_id'],
        config['aws_secret_access_key'],
        config['play_name'],
        "edx",
        "stage",
        base_ami_id
    )

    return pipeline


def build_migrate_deploy_subset_pipeline(
    gcc, prerelease_materials, bmd_steps, variable_files, cmd_line_vars, pipeline_group,
    pipeline_name, app_repo, theme_url, configuration_secure_repo, configuration_internal_repo,
    configuration_url,
    auto_deploy_ami=False, auto_run=False):
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
    # Sort the BMD steps by the custom 'bmd' alphabet
    bmd_steps = utils.sort_bmd(bmd_steps.lower())

    # validate the caller has requested a valid pipeline configuration
    utils.validate_pipeline_permutations(bmd_steps)

    # Merge the configuration files/variables together
    config = utils.merge_files_and_dicts(variable_files, list(cmd_line_vars,))

    # Some pipelines will need to know the name of the upstream pipeline that built the AMI.
    # Determine the build pipeline name and add it to the config.
    pipeline_name, pipeline_name_build = utils.determine_pipeline_names(pipeline_name, bmd_steps)
    if 'pipeline_name_build' in config:
        raise Exception("The config 'pipeline_name_build' value exists but should only be programmatically generated!")

    BMD_STAGES = {
        'b': partial(
            generate_build_stages,
            app_repo=app_repo,
            theme_url=theme_url,
            configuration_secure_repo=configuration_secure_repo,
            configuration_internal_repo=configuration_internal_repo,
            configuration_url=configuration_url,
        ),
        'm': generate_migrate_stages,
        'd': partial(
            generate_deploy_stages,
            pipeline_name_build=pipeline_name_build,
            auto_deploy_ami=auto_deploy_ami
        )
    }

    pipeline = gcc.ensure_pipeline_group(pipeline_group)\
                  .ensure_replacement_of_pipeline(pipeline_name)

    # We always need to launch the AMI, independent deploys are done with a different pipeline
    # if the pipeline has a migrate stage, but no building stages, look up the build information from the
    # upstream pipeline.
    ami_artifact = None
    if 'm' in bmd_steps and 'b' not in bmd_steps:
        ami_artifact = utils.ArtifactLocation(
            pipeline_name_build,
            constants.BUILD_AMI_STAGE_NAME,
            constants.BUILD_AMI_JOB_NAME,
            FetchArtifactFile(constants.BUILD_AMI_FILENAME)
        )
    else:
        ami_artifact = utils.ArtifactLocation(
            prerelease_materials.name,
            "select_base_ami",
            "select_base_ami_job",
            FetchArtifactFile("ami_override.yml"),
        )

    launch_stage = stages.generate_launch_instance(
        pipeline,
        config['aws_access_key_id'],
        config['aws_secret_access_key'],
        config['ec2_vpc_subnet_id'],
        config['ec2_security_group_id'],
        config['ec2_instance_profile_name'],
        config['base_ami_id'],
        upstream_build_artifact=ami_artifact,
        manual_approval=not auto_run
    )

    # Generate all the requested stages
    for phase in bmd_steps:
        BMD_STAGES[phase](pipeline, config)

    # Add the cleanup stage
    generate_cleanup_stages(pipeline, config, pipeline_name_build)

    return pipeline


def generate_build_stages(pipeline, config, app_repo, theme_url, configuration_secure_repo,
                          configuration_internal_repo, configuration_url):
    stages.generate_run_play(
        pipeline,
        'playbooks/edx-east/edxapp.yml',
        play=config['play_name'],
        deployment=config['edx_deployment'],
        edx_environment=config['edx_environment'],
        private_github_key=config['github_private_key'],
        app_repo=app_repo,
        configuration_secure_dir='{}-secure'.format(config['edx_deployment']),
        configuration_internal_dir='{}-internal'.format(config['edx_deployment']),
        hipchat_token=config['hipchat_token'],
        hipchat_room='release',
        edx_platform_version='$GO_REVISION_EDX_PLATFORM',
        edx_platform_repo='$APP_REPO',
        configuration_version='$GO_REVISION_CONFIGURATION',
        edxapp_theme_source_repo=theme_url,
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
        app_repo=app_repo,
        app_version='$GO_REVISION_EDX_PLATFORM',
        configuration_secure_repo=configuration_secure_repo,
        configuration_internal_repo=configuration_internal_repo,
        configuration_repo=configuration_url,
        hipchat_token=config['hipchat_token'],
        hipchat_room='release pipeline',
        configuration_version='$GO_REVISION_CONFIGURATION',
        configuration_secure_version='$GO_REVISION_{}_SECURE'.format(config['edx_deployment'].upper()),
        configuration_internal_version='$GO_REVISION_{}_SECURE'.format(config['edx_deployment'].upper()),
        aws_access_key_id=config['aws_access_key_id'],
        aws_secret_access_key=config['aws_secret_access_key'],
        edxapp_theme_source_repo=theme_url,
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


def generate_deploy_stages(pipeline, config, pipeline_name_build, auto_deploy_ami=False):
    #
    # Create the stage to deploy the AMI.
    #
    ami_file_location = utils.ArtifactLocation(
        pipeline_name_build,
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
        manual_approval=not auto_deploy_ami
    )
    return pipeline


def generate_cleanup_stages(pipeline, config, pipeline_name_build):
    #
    # Create the stage to terminate the EC2 instance used to both build the AMI and run DB migrations.
    #
    instance_info_location = utils.ArtifactLocation(
        pipeline_name_build,
        constants.LAUNCH_INSTANCE_STAGE_NAME,
        constants.LAUNCH_INSTANCE_JOB_NAME,
        constants.LAUNCH_INSTANCE_FILENAME
    )
    stages.generate_terminate_instance(
        pipeline,
        instance_info_location,
        aws_access_key_id=config['aws_access_key_id'],
        aws_secret_access_key=config['aws_secret_access_key'],
        hipchat_token=config['hipchat_token'],
        runif='any'
    )
    return pipeline
