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
    Generates 2 pipelines used to deploy the discovery service to stage, loadtest, and prod.

    The first pipeline contains 2 stages:

        1. Build AMIs.

        2. Migrate and deploy to stage. For increased concurrency, this stage
           may be broken into separate migration and deployment stages.

    The second pipeline contains 4 stages:

        1. Armed stage. Triggered by success of the last stage in the preceding pipeline.
           Can be armed by the earlier prod AMI build to provide a fast track to prod.

        2. Migrate and deploy to prod. Requires manual execution.

        3. Roll back prod ASGs (code). Requires manual execution.

        4. Roll back prod migrations. Requires manual execution. (Pipeline operators
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

    build_pipeline = pipeline_group.ensure_replacement_of_pipeline('-'.join(['build', edp.play]))

    # Downstream tasks expect a material named configuration-secure.
    configuration_secure_material = materials.deployment_secure(
        edp.deployment,
        destination_directory='configuration-secure'
    )

    ensured_materials = [
        materials.TUBULAR(),
        materials.CONFIGURATION(),
        configuration_secure_material,
        materials.deployment_internal(edp.deployment),
        GitMaterial(
            app_repo_url,
            branch='master',
            polling=True,
            destination_directory=edp.play
        ),
    ]

    for material in ensured_materials:
        build_pipeline.ensure_material(material)

    build_pipeline.ensure_environment_variables({
        'APPLICATION_USER': edp.play,
        'APPLICATION_NAME': edp.play,
        'APPLICATION_PATH': '/edx/app/' + edp.play,
    })

    build_stage = build_pipeline.ensure_stage(constants.BUILD_AMIS_STAGE_NAME)
    for environment in ('stage', 'loadtest', 'prod'):
        jobs.generate_build_ami(
            build_pipeline,
            build_stage,
            edp._replace(environment=environment),
            app_repo_url,
            configuration_secure_material.url,
            playbook_path,
            env_configs[environment],
            app_version=app_version_var,
            DISCOVERY_VERSION=app_version_var,
        )

    deploy_stage = build_pipeline.ensure_stage(constants.DEPLOY_AMIS_STAGE_NAME)
    # TODO: Add loadtest to this tuple once deploys to stage actually go to stage.
    for environment in ('stage',):
        jobs.generate_deploy_ami(
            build_pipeline,
            deploy_stage,
            edp._replace(environment=environment),
            env_configs[environment],
        )


if __name__ == '__main__':
    pipeline_script(install_pipelines, environments=('stage', 'loadtest', 'prod'))
