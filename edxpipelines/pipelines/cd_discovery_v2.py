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
from edxpipelines.pipelines.script import pipeline_script
from edxpipelines.utils import EDP


def install_pipelines(configurator, config, env_configs):  # pylint: disable=unused-argument
    """
    Generates 2 pipelines used to deploy the discovery service to stage and prod.

    The first pipeline contains 2 stages, run serially:

        1. Build AMIs. Contains 2 jobs, run in parallel.

            a. Build stage AMI. Contains 5 tasks, run serially:
                i.   Select base AMI.
                ii.  Launch a new instance on which we will build an AMI.
                iii. Run the Ansible play for the service.
                iv.  Create a stage AMI based on the instance.
                v.   Regardless of job state: clean up instance.

            b. Build prod AMI. Contains 5 tasks, run serially:
                i.   Select base AMI.
                ii.  Launch a new instance on which we will build an AMI.
                iii. Run the Ansible play for the service.
                iv.  Create a prod AMI based on the instance.
                v.   Regardless of job state: clean up instance.

        2. Migrate and deploy to stage. Contains 1 job.

            a. Migrate and deploy to stage. Contains 4+ tasks, run serially:
                i.   Launch instance of stage AMI built in the previous stage.
                ii.  Run migrations against stage.
                iii. Any post-migration tasks (e.g., running management commands).
                iv.  Deploy the stage AMI.
                v.   Regardless of job state: clean up instance.

    The second pipeline contains 4 stages, run serially:

        1. Armed stage. Triggered by success of the last stage in the preceding pipeline.
           Can be armed by the earlier prod AMI build to provide a fast track to prod.

        2. Migrate and deploy to prod. Requires manual execution. Contains 1 job.

            a. Migrate and deploy to prod. Contains 4+ tasks, run serially:
                i.   Launch instance of prod AMI built in the previous pipeline.
                ii.  Run migrations against prod.
                iii. Any post-migration tasks (e.g., running management commands).
                iv.  Deploy the prod AMI.
                v.   Regardless of job state: clean up instance.

        3. Roll back prod ASGs (code). Requires manual execution.

        4. Roll back prod migrations.
    """
    edp = EDP(None, 'edx', 'discovery')
    app_repo_url = 'https://github.com/edx/course-discovery.git'
    app_version_var = '$GO_REVISION_DISCOVERY'
    playbook_path = 'playbooks/edx-east/discovery.yml'

    configurator.ensure_removal_of_pipeline_group(edp.play)
    pipeline_group = configurator.ensure_pipeline_group(edp.play)

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

    for environment in ('stage', 'prod'):
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


if __name__ == '__main__':
    pipeline_script(install_pipelines)
