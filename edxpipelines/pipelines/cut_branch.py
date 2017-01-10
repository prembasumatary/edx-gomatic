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
def install_pipelines(save_config_locally, dry_run, variable_files, cmd_line_vars):
    """
    Variables needed for this pipeline:
    - pipeline_name
    - pipeline_group
    - git_token
    - org
    - repo
    - source_branch
    - target_branch
    - materials (list): a list of materials this pipeline should monitor
    - cron: the cron this pipeline should run against
    """
    config = utils.merge_files_and_dicts(variable_files, list(cmd_line_vars,))

    gcc = GoCdConfigurator(
        HostRestClient(
            config['gocd_url'],
            config['gocd_username'],
            config['gocd_password'],
            ssl=True)
    )
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

    stages.generate_create_branch(
        pipeline,
        constants.GIT_CREATE_BRANCH_STAGE_NAME,
        config['org'],
        config['repo'],
        config['source_branch'],
        config['target_branch'],
        config['git_token'],
        manual_approval=True
    )
    pipeline.set_timer(config['cron'], True)
    gcc.save_updated_config(save_config_locally=save_config_locally, dry_run=dry_run)


if __name__ == "__main__":
    install_pipelines()
