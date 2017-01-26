#!/usr/bin/env python
import sys
from os import path
import click
from gomatic import *

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

from edxpipelines import utils
from edxpipelines import constants
from edxpipelines.patterns import stages


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
    materials: List of dictionaries of the materials used in this pipeline
    upstream_pipelines: List of dictionaries of the upstream piplines that feed in to the rollback pipeline.
    """
    config = utils.merge_files_and_dicts(variable_files, list(cmd_line_vars,))

    gcc = GoCdConfigurator(HostRestClient(config['gocd_url'], config['gocd_username'], config['gocd_password'], ssl=True))
    pipeline = gcc.ensure_pipeline_group(config['pipeline_group'])\
                  .ensure_replacement_of_pipeline(config['pipeline_name'])\
                  .ensure_environment_variables({'WAIT_SLEEP_TIME': config['tubular_sleep_wait_time']})

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

    # Specify the upstream deploy pipeline material for this rollback pipeline.
    # Assumes there's only a single upstream pipeline material for this pipeline.
    rollback_material = config['upstream_pipeline']
    pipeline.ensure_material(
        PipelineMaterial(
            pipeline_name=rollback_material['pipeline_name'],
            stage_name=rollback_material['stage_name'],
            material_name=rollback_material['material_name']
        )
    )

    # Specify the artifact that will be fetched containing the previous deployment information.
    # Assumes there's only a single upstream artifact used by this pipeline.
    artifact_config = config['upstream_deploy_artifact']
    deploy_file_location = utils.ArtifactLocation(
        artifact_config['pipeline_name'],
        artifact_config['stage_name'],
        artifact_config['job_name'],
        artifact_config['artifact_name']
    )

    # Create the armed stage as this pipeline needs to auto-execute
    stages.generate_armed_stage(pipeline, constants.ARMED_JOB_NAME)

    # Create a single stage in the pipeline which will rollback to the previous ASGs/AMI.
    rollback_stage = stages.generate_rollback_asg_stage(
        pipeline,
        config['asgard_api_endpoints'],
        config['asgard_token'],
        config['aws_access_key_id'],
        config['aws_secret_access_key'],
        config['hipchat_token'],
        constants.HIPCHAT_ROOM,
        deploy_file_location,
    )
    # Since we only want this stage to rollback via manual approval, ensure that it is set on this stage.
    rollback_stage.set_has_manual_approval()

    gcc.save_updated_config(save_config_locally=save_config_locally, dry_run=dry_run)

if __name__ == "__main__":
    install_pipeline()
