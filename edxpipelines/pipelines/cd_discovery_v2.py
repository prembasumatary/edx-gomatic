#!/usr/bin/env python
"""
Script to install pipelines to deploy the course-discovery IDA.
"""
import sys
from os import path

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

# pylint: disable=wrong-import-position
from gomatic import GitMaterial

from edxpipelines import constants, materials
from edxpipelines.patterns import jobs
from edxpipelines.patterns.authz import Permission, ensure_permissions
from edxpipelines.pipelines.script import pipeline_script
from edxpipelines.utils import EDP


def install_pipelines(configurator, config, env_configs):  # pylint: disable=unused-argument
    """
    Generates a pipeline used to deploy the discovery service to stage, loadtest, and prod.

    The pipeline contains the following stages:

        1. Build AMIs.

        2. Migrate and deploy to stage and loadtest. For improved concurrency, this stage
           may be broken into separate migration and deployment stages.

        3. Migrate and deploy to prod. Requires manual approval.

        4. Roll back prod ASGs (code). Requires manual approval.

        5. Roll back prod migrations. Requires manual approval. (Pipeline operators
           won't always want to roll back migrations.)
    """
    edp = EDP(None, 'edx', 'discovery')
    app_repo_url = 'https://github.com/edx/course-discovery.git'
    app_version_var = '$GO_REVISION_DISCOVERY'
    playbook_path = 'playbooks/edx-east/discovery.yml'

    configurator.ensure_removal_of_pipeline_group(edp.play)
    pipeline_group = configurator.ensure_pipeline_group(edp.play)

    admin_role = '-'.join([edp.play, 'admin'])
    ensure_permissions(configurator, pipeline_group, Permission.ADMINS, [admin_role])

    operator_role = '-'.join([edp.play, 'operator'])
    ensure_permissions(configurator, pipeline_group, Permission.OPERATE, [operator_role])
    ensure_permissions(configurator, pipeline_group, Permission.VIEW, [operator_role])

    pipeline = pipeline_group.ensure_replacement_of_pipeline(edp.play)

    configuration_secure_material = materials.deployment_secure(
        edp.deployment,
        destination_directory='configuration-secure'
    )
    configuration_internal_material = materials.deployment_internal(
        edp.deployment,
        destination_directory='configuration-internal'
    )
    app_material = GitMaterial(
        app_repo_url,
        material_name=edp.play,
        branch='master',
        polling=True,
        destination_directory=edp.play
    )

    ensured_materials = [
        materials.TUBULAR(),
        materials.CONFIGURATION(),
        configuration_secure_material,
        configuration_internal_material,
        app_material,
    ]

    for material in ensured_materials:
        pipeline.ensure_material(material)

    pipeline.ensure_environment_variables({
        'APPLICATION_USER': edp.play,
        'APPLICATION_NAME': edp.play,
        'APPLICATION_PATH': '/edx/app/' + edp.play,
        'DB_MIGRATION_USER': constants.DB_MIGRATION_USER,
    })

    pipeline.set_label_template(constants.BUILD_LABEL_TPL(app_material))

    build_stage = pipeline.ensure_stage(constants.BUILD_AMIS_STAGE_NAME)
    for environment in ('stage', 'loadtest', 'prod'):
        jobs.generate_build_ami(
            pipeline,
            build_stage,
            edp._replace(environment=environment),
            app_repo_url,
            configuration_secure_material,
            configuration_internal_material,
            playbook_path,
            env_configs[environment],
            app_version=app_version_var,
            DISCOVERY_VERSION=app_version_var,
        )

    pre_prod_deploy_stage = pipeline.ensure_stage('_'.join(['pre_prod', constants.DEPLOY_AMIS_STAGE_NAME]))
    # TODO: When development is complete, these jobs will be created for stage and loadtest.
    for environment in ('loadtest',):
        jobs.generate_deploy_ami(
            pipeline,
            pre_prod_deploy_stage,
            edp._replace(environment=environment),
            env_configs[environment],
        )

    prod_deploy_stage = pipeline.ensure_stage('_'.join(['prod', constants.DEPLOY_AMI_STAGE_NAME]))
    prod_deploy_stage.set_has_manual_approval()
    # TODO: When development is complete, this job will be created for prod.
    jobs.generate_deploy_ami(
        pipeline,
        prod_deploy_stage,
        edp._replace(environment='loadtest'),
        env_configs['loadtest'],
    )


if __name__ == '__main__':
    pipeline_script(install_pipelines, environments=('stage', 'loadtest', 'prod'))
