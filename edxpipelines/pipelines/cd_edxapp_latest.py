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
from edxpipelines.patterns import edxapp
from edxpipelines.materials import (
    TUBULAR, CONFIGURATION, EDX_PLATFORM, EDX_SECURE, EDGE_SECURE,
    EDX_MICROSITE, EDX_INTERNAL, EDGE_INTERNAL
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
    stage_config = utils.merge_files_and_dicts(variable_files + stage_variable_files, list(cmd_line_vars))
    prod_edx_config = utils.merge_files_and_dicts(variable_files + prod_edx_variable_files, list(cmd_line_vars))
    prod_edge_config = utils.merge_files_and_dicts(variable_files + prod_edge_variable_files, list(cmd_line_vars))

    # Create the pipeline
    gcc = GoCdConfigurator(HostRestClient(config['gocd_url'], config['gocd_username'], config['gocd_password'], ssl=True))
    edxapp_group = gcc.ensure_pipeline_group('edxapp')
    edxapp_deploy_group = gcc.ensure_pipeline_group('edxapp_prod_deploys')

    cut_branch = edxapp.cut_branch(edxapp_group, variable_files, cmd_line_vars)
    prerelease_materials = edxapp.prerelease_materials(edxapp_group, variable_files + stage_variable_files, cmd_line_vars)

    stage_b = edxapp.build_migrate_deploy_subset_pipeline(
        edxapp_group,
        [
            edxapp.generate_build_stages(
                app_repo=EDX_PLATFORM.url,
                theme_url=EDX_MICROSITE.url,
                configuration_secure_repo=EDX_SECURE.url,
                configuration_internal_repo=EDX_INTERNAL.url,
                configuration_url=CONFIGURATION.url,
            ),
        ],
        config=stage_config,
        pipeline_name="STAGE_edxapp_B",
        ami_artifact=None,
        auto_run=True,
    )

    stage_md = edxapp.build_migrate_deploy_subset_pipeline(
        edxapp_group,
        [
            edxapp.generate_migrate_stages,
            edxapp.generate_deploy_stages(
                pipeline_name_build=stage_b.name,
                auto_deploy_ami=True,
            ),
            edxapp.generate_e2e_test_stage,
        ],
        config=stage_config,
        pipeline_name="STAGE_edxapp_M-D",
        ami_artifact=None,
        auto_run=True,
    )
    stage_md.set_automatic_pipeline_locking()

    stage_md.ensure_material(
        PipelineMaterial(
            pipeline_name=stage_b.name,
            stage_name=constants.BUILD_AMI_STAGE_NAME,
            material_name="stage_ami_build",
        )
    )

    prod_edx_b = edxapp.build_migrate_deploy_subset_pipeline(
        edxapp_deploy_group,
        [
            edxapp.generate_build_stages(
                app_repo=EDX_PLATFORM.url,
                theme_url=EDX_MICROSITE.url,
                configuration_secure_repo=EDX_SECURE.url,
                configuration_internal_repo=EDX_INTERNAL.url,
                configuration_url=CONFIGURATION.url,
            ),
        ],
        config=prod_edx_config,
        pipeline_name="PROD_edx_edxapp_B",
        ami_artifact=None,
        auto_run=True,
    )

    prod_edge_b = edxapp.build_migrate_deploy_subset_pipeline(
        edxapp_deploy_group,
        [
            edxapp.generate_build_stages(
                app_repo=EDX_PLATFORM.url,
                theme_url=EDX_MICROSITE.url,
                configuration_secure_repo=EDGE_SECURE.url,
                configuration_internal_repo=EDGE_INTERNAL.url,
                configuration_url=CONFIGURATION.url,
            ),
        ],
        config=prod_edge_config,
        pipeline_name="PROD_edge_edxapp_B",
        ami_artifact=None,
        auto_run=True,
    )

    for pipeline in (stage_b, prod_edx_b, prod_edge_b):
        pipeline.ensure_material(
            PipelineMaterial(
                pipeline_name=prerelease_materials.name,
                stage_name=constants.ARM_PRERELEASE_STAGE,
                material_name="prerelease",
            )
        )

    manual_verification = edxapp.manual_verification(edxapp_deploy_group, variable_files, cmd_line_vars)

    manual_verification.ensure_material(
        PipelineMaterial(
            pipeline_name=stage_md.name,
            stage_name=constants.DEPLOY_AMI_STAGE_NAME,
            material_name='stage_ami_deploy',
        )
    )

    manual_verification.ensure_material(
        PipelineMaterial(
            pipeline_name=prod_edx_b.name,
            stage_name=constants.BUILD_AMI_STAGE_NAME,
            material_name='PROD_edx_edxapp_ami_build',
        )
    )

    manual_verification.ensure_material(
        PipelineMaterial(
            pipeline_name=prod_edge_b.name,
            stage_name=constants.BUILD_AMI_STAGE_NAME,
            material_name='PROD_edge_edxapp_ami_build',
        )
    )

    # When manually triggered in the pipeline above, the following two pipelines migrate/deploy
    # to the production EDX and EDGE environments.

    prod_edx_md = edxapp.build_migrate_deploy_subset_pipeline(
        edxapp_deploy_group,
        [
            edxapp.generate_migrate_stages,
            edxapp.generate_deploy_stages(
                pipeline_name_build=prod_edx_b.name,
                auto_deploy_ami=True,
            )
        ],
        config=prod_edx_config,
        pipeline_name="PROD_edx_edxapp_M-D",
        ami_artifact=utils.ArtifactLocation(
            prod_edx_b.name,
            constants.BUILD_AMI_STAGE_NAME,
            constants.BUILD_AMI_JOB_NAME,
            FetchArtifactFile(constants.BUILD_AMI_FILENAME)
        ),
        auto_run=True,
    )

    prod_edx_md.ensure_material(
        PipelineMaterial(prod_edx_b.name, "build_ami", "prod_edx_ami_build")
    )

    prod_edge_md = edxapp.build_migrate_deploy_subset_pipeline(
        edxapp_deploy_group,
        [
            edxapp.generate_migrate_stages,
            edxapp.generate_deploy_stages(
                pipeline_name_build=prod_edge_b.name,
                auto_deploy_ami=True,
            )
        ],
        config=prod_edge_config,
        pipeline_name="PROD_edge_edxapp_M-D",
        ami_artifact=utils.ArtifactLocation(
            prod_edge_b.name,
            constants.BUILD_AMI_STAGE_NAME,
            constants.BUILD_AMI_JOB_NAME,
            FetchArtifactFile(constants.BUILD_AMI_FILENAME)
        ),
        auto_run=True,
    )

    prod_edge_md.ensure_material(
        PipelineMaterial(prod_edge_b.name, "build_ami", "prod_edge_ami_build")
    )

    for pipeline in (prod_edx_md, prod_edge_md):
        pipeline.ensure_material(
            PipelineMaterial(
                pipeline_name=manual_verification.name,
                stage_name=constants.MANUAL_VERIFICATION_STAGE_NAME,
                material_name="prod_release_gate",
            )
        )

    for pipeline in (stage_b, stage_md, prod_edx_b, prod_edx_md, prod_edge_b, prod_edge_md):
        for material in (
            TUBULAR, CONFIGURATION, EDX_PLATFORM, EDX_SECURE, EDGE_SECURE,
            EDX_MICROSITE, EDX_INTERNAL, EDGE_INTERNAL
        ):
            pipeline.ensure_material(material)

    rollback_edx = edxapp.rollback_asgs(
        edxapp_deploy_group,
        'PROD_edx_edxapp_Rollback_latest',
        prod_edx_md,
        variable_files + prod_edx_variable_files,
        cmd_line_vars
    )
    rollback_edge = edxapp.rollback_asgs(
        edxapp_deploy_group,
        'PROD_edge_edxapp_Rollback_latest',
        prod_edge_md,
        variable_files + prod_edge_variable_files,
        cmd_line_vars
    )

    gcc.save_updated_config(save_config_locally=save_config_locally, dry_run=dry_run)

if __name__ == "__main__":
    install_pipelines()
