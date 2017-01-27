#!/usr/bin/env python
from itertools import groupby
import sys
from os import path
import click
from gomatic import *

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

from edxpipelines import utils
from edxpipelines.patterns import stages
from edxpipelines.patterns import pipelines
from edxpipelines import constants
from edxpipelines.patterns.authz import Permission, ensure_permissions
from edxpipelines.patterns import edxapp
from edxpipelines.pipelines.script import pipeline_script
from edxpipelines.materials import (
    TUBULAR, CONFIGURATION, EDX_PLATFORM, EDX_SECURE, EDGE_SECURE,
    EDX_MICROSITE, EDX_INTERNAL, EDGE_INTERNAL
)


@pipeline_script
def install_pipelines(save_config_locally, dry_run, variable_files,
                      env_variable_files, cmd_line_vars):
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
    env_vars = {
        env: tuple(file for _, file in files)
        for env, files
        in groupby(
            sorted(env_variable_files),
            lambda (env, file): env,
        )
    }
    env_configs = {
        env: utils.merge_files_and_dicts(variable_files + files, list(cmd_line_vars))
        for env, files in env_vars.items()
    }

    # Create the pipeline
    gcc = GoCdConfigurator(HostRestClient(config['gocd_url'], config['gocd_username'], config['gocd_password'], ssl=True))
    gcc.ensure_removal_of_pipeline_group('edxapp')
    gcc.ensure_removal_of_pipeline_group('edxapp_prod_deploys')
    edxapp_group = gcc.ensure_pipeline_group('edxapp')

    ensure_permissions(edxapp_group, Permission.OPERATE, ['edxapp-operator'])
    ensure_permissions(edxapp_group, Permission.VIEW, ['edxapp-operator'])

    edxapp_deploy_group = gcc.ensure_pipeline_group('edxapp_prod_deploys')

    ensure_permissions(edxapp_deploy_group, Permission.ADMINS, ['deploy'])
    ensure_permissions(edxapp_deploy_group, Permission.OPERATE, ['prod-deploy-operators'])
    ensure_permissions(edxapp_deploy_group, Permission.VIEW, ['prod-deploy-operators'])

    cut_branch = edxapp.cut_branch(
        edxapp_group,
        config,
    )
    prerelease_materials = edxapp.prerelease_materials(
        edxapp_group,
        env_configs['stage'],
    )

    stage_b = edxapp.build_migrate_deploy_subset_pipeline(
        edxapp_group,
        [
            edxapp.generate_build_stages(
                app_repo=EDX_PLATFORM().url,
                theme_url=EDX_MICROSITE().url,
                configuration_secure_repo=EDX_SECURE().url,
                configuration_internal_repo=EDX_INTERNAL().url,
                configuration_url=CONFIGURATION().url,
            ),
        ],
        config=env_configs['stage'],
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
        ],
        post_cleanup_builders=[
            edxapp.generate_e2e_test_stage,
        ],
        config=env_configs['stage'],
        pipeline_name="STAGE_edxapp_M-D",
        ami_artifact=utils.ArtifactLocation(
            stage_b.name,
            constants.BUILD_AMI_STAGE_NAME,
            constants.BUILD_AMI_JOB_NAME,
            FetchArtifactFile(constants.BUILD_AMI_FILENAME)
        ),
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
                app_repo=EDX_PLATFORM().url,
                theme_url=EDX_MICROSITE().url,
                configuration_secure_repo=EDX_SECURE().url,
                configuration_internal_repo=EDX_INTERNAL().url,
                configuration_url=CONFIGURATION().url,
            ),
        ],
        config=env_configs['prod-edx'],
        pipeline_name="PROD_edx_edxapp_B",
        ami_artifact=None,
        auto_run=True,
    )

    prod_edge_b = edxapp.build_migrate_deploy_subset_pipeline(
        edxapp_deploy_group,
        [
            edxapp.generate_build_stages(
                app_repo=EDX_PLATFORM().url,
                theme_url=EDX_MICROSITE().url,
                configuration_secure_repo=EDGE_SECURE().url,
                configuration_internal_repo=EDGE_INTERNAL().url,
                configuration_url=CONFIGURATION().url,
            ),
        ],
        config=env_configs['prod-edge'],
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

    manual_verification = edxapp.manual_verification(
        edxapp_deploy_group,
        config,
    )

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
        config=env_configs['prod-edx'],
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
        config=env_configs['prod-edge'],
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
            pipeline.ensure_material(material())

    rollback_edx = edxapp.rollback_asgs(
        edxapp_deploy_group,
        'PROD_edx_edxapp_Rollback_latest',
        prod_edx_b,
        prod_edx_md,
        env_configs['prod-edx'],
    )
    rollback_edge = edxapp.rollback_asgs(
        edxapp_deploy_group,
        'PROD_edge_edxapp_Rollback_latest',
        prod_edge_b,
        prod_edge_md,
        env_configs['prod-edge'],
    )

    deploy_artifact = utils.ArtifactLocation(
        prod_edx_md.name,
        constants.DEPLOY_AMI_STAGE_NAME,
        constants.DEPLOY_AMI_JOB_NAME,
        FetchArtifactFile(constants.DEPLOY_AMI_OUT_FILENAME)
    )

    merge_back = edxapp.merge_back_branches(
        edxapp_deploy_group,
        constants.BRANCH_CLEANUP_PIPELINE_NAME,
        deploy_artifact,
        config,
    )

    # Specify the upstream deploy pipeline materials for this branch-merging pipeline.
    for deploy_pipeline in (prod_edx_md, prod_edge_md):
        merge_back.ensure_material(
            PipelineMaterial(
                pipeline_name=deploy_pipeline.name,
                stage_name=constants.DEPLOY_AMI_STAGE_NAME,
                material_name='deploy_pipeline_{}'.format(deploy_pipeline.name),
            )
        )

    gcc.save_updated_config(save_config_locally=save_config_locally, dry_run=dry_run)

if __name__ == "__main__":
    install_pipelines()
