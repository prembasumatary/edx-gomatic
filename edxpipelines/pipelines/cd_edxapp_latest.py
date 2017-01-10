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
from edxpipelines.pipelines import edxapp_pipelines
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
    '--stage-variable-file', 'stage_variable_files',
    multiple=True,
    help='Path to yaml variable file with a dictionary of key/value pairs '
         'to be used as variables in the script, scoped to the stage environment.',
    required=False,
    default=[]
)
@click.option(
    '--prod-edge-variable-file', 'prod_edge_variable_files',
    multiple=True,
    help='Path to yaml variable file with a dictionary of key/value pairs '
         'to be used as variables in the script, scoped to the prod-edge environment.',
    required=False,
    default=[]
)
@click.option(
    '--prod-edx-variable-file', 'prod_edx_variable_files',
    multiple=True,
    help='Path to yaml variable file with a dictionary of key/value pairs '
         'to be used as variables in the script, scoped to the prod-edx environment.',
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
def install_pipelines(save_config_locally, dry_run, variable_files,
                      stage_variable_files, prod_edx_variable_files,
                      prod_edge_variable_files, cmd_line_vars):
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

    # Merge the configuration files/variables together
    config = utils.merge_files_and_dicts(variable_files, list(cmd_line_vars,))

    # Create the pipeline
    gcc = GoCdConfigurator(HostRestClient(config['gocd_url'], config['gocd_username'], config['gocd_password'], ssl=True))

    cut_branch = edxapp_pipelines.cut_branch(gcc, variable_files, cmd_line_vars)

    stage_bmd = edxapp_pipelines.build_migrate_deploy_subset_pipeline(
        gcc,
        bmd_steps="bmd",
        variable_files=variable_files + stage_variable_files,
        cmd_line_vars=cmd_line_vars,
        pipeline_group="edxapp",
        pipeline_name="STAGE_edxapp",
        app_repo=EDX_PLATFORM.url,
        theme_url=EDX_MICROSITE.url,
        configuration_secure_repo=EDX_SECURE.url,
        configuration_internal_repo=EDX_INTERNAL.url,
        configuration_url=CONFIGURATION.url,
        auto_run=True,
        auto_deploy_ami=True,
    )
    
    prod_edx_b = edxapp_pipelines.build_migrate_deploy_subset_pipeline(
        gcc,
        bmd_steps="b",
        variable_files=variable_files + prod_edx_variable_files,
        cmd_line_vars=cmd_line_vars,
        pipeline_group="edxapp_prod_deploys",
        pipeline_name="PROD_edx_edxapp",
        app_repo=EDX_PLATFORM.url,
        theme_url=EDX_MICROSITE.url,
        configuration_secure_repo=EDX_SECURE.url,
        configuration_internal_repo=EDX_INTERNAL.url,
        configuration_url=CONFIGURATION.url,
        auto_run=True,
        auto_deploy_ami=True,
    )

    prod_edge_b = edxapp_pipelines.build_migrate_deploy_subset_pipeline(
        gcc,
        bmd_steps="b",
        variable_files=variable_files + prod_edge_variable_files,
        cmd_line_vars=cmd_line_vars,
        pipeline_group="edxapp_prod_deploys",
        pipeline_name="PROD_edge_edxapp",
        app_repo=EDX_PLATFORM.url,
        theme_url=EDX_MICROSITE.url,
        configuration_secure_repo=EDGE_SECURE.url,
        configuration_internal_repo=EDGE_INTERNAL.url,
        configuration_url=CONFIGURATION.url,
        auto_run=True,
        auto_deploy_ami=True,
    )

    for pipeline in (stage_bmd, prod_edx_b, prod_edge_b):
        pipeline.ensure_material(
            PipelineMaterial(
                pipeline_name="prerelease_edxapp_materials_latest",
                stage_name="select_base_ami",
                material_name="prerelease",
            )
        )


  # When manually triggered in the pipeline above, the following two pipelines migrate/deploy
  # to the production EDX and EDGE environments.

    prod_edx_md = edxapp_pipelines.build_migrate_deploy_subset_pipeline(
        gcc,
        bmd_steps="md",
        variable_files=variable_files + prod_edx_variable_files, 
        cmd_line_vars=cmd_line_vars,
        pipeline_group="edxapp_prod_deploys",
        pipeline_name="PROD_edx_edxapp",
        app_repo=EDX_PLATFORM.url,
        theme_url=EDX_MICROSITE.url,
        configuration_secure_repo=EDX_SECURE.url,
        configuration_internal_repo=EDX_INTERNAL.url,
        configuration_url=CONFIGURATION.url,
        auto_run=True,
        auto_deploy_ami=True,
    )

    prod_edx_md.ensure_material(
        PipelineMaterial(prod_edx_b.name, "build_ami", "prod_edx_ami_build")
    )

    prod_edge_md = edxapp_pipelines.build_migrate_deploy_subset_pipeline(
        gcc,
        bmd_steps="md",
        variable_files=variable_files + prod_edge_variable_files,
        cmd_line_vars=cmd_line_vars,
        pipeline_group="edxapp_prod_deploys",
        pipeline_name="PROD_edge_edxapp",
        app_repo=EDX_PLATFORM.url,
        theme_url=EDX_MICROSITE.url,
        configuration_secure_repo=EDGE_SECURE.url,
        configuration_internal_repo=EDGE_INTERNAL.url,
        configuration_url=CONFIGURATION.url,
        auto_run=True,
        auto_deploy_ami=True,
    )

    prod_edge_md.ensure_material(
        PipelineMaterial(prod_edge_b.name, "build_ami", "prod_edge_ami_build")
    )

    for pipeline in (prod_edx_md, prod_edge_md):
        pipeline.ensure_material(
            PipelineMaterial(
                pipeline_name="manual_verification_edxapp_prod_early_ami_build",
                stage_name="manual_verification",
                material_name="prod_release_gate",
            )
        )

    for pipeline in (stage_bmd, prod_edx_b, prod_edx_md, prod_edge_b, prod_edge_md):
        for material in (
            TUBULAR, CONFIGURATION, EDX_PLATFORM, EDX_SECURE, EDGE_SECURE, MCKINSEY_SECURE,
            EDX_MICROSITE, EDX_INTERNAL, EDGE_INTERNAL, MCKINSEY_INTERNAL
        ):
            pipeline.ensure_material(material)

    gcc.save_updated_config(save_config_locally=save_config_locally, dry_run=dry_run)

if __name__ == "__main__":
    install_pipelines()
