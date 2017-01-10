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
from edxpipelines.materials import (
    TUBULAR, CONFIGURATION, EDX_PLATFORM, EDX_SECURE, EDGE_SECURE, MCKINSEY_SECURE,
    EDX_MICROSITE, EDX_INTERNAL, EDGE_INTERNAL, MCKINSEY_INTERNAL
)


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
def install_pipelines(save_config_locally, dry_run, variable_files, cmd_line_vars):
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

    gcc.save_updated_config(save_config_locally=save_config_locally, dry_run=dry_run)


if __name__ == "__main__":
    install_pipelines()
