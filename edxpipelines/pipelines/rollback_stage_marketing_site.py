#!/usr/bin/env python
"""
Script to install pipelines that can rollback the stage edx-mktg site.
"""
import sys
from os import path

from gomatic import PipelineMaterial, FetchArtifactFile, FetchArtifactTask

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

# pylint: disable=wrong-import-position
from edxpipelines import constants
from edxpipelines.patterns import tasks
from edxpipelines.pipelines.script import pipeline_script
from edxpipelines.materials import (TUBULAR, EDX_MKTG, ECOM_SECURE)


def install_pipelines(configurator, config, env_configs):  # pylint: disable=unused-argument
    """
    Install pipelines that can rollback the stage edx-mktg site.
    """
    pipeline = configurator \
        .ensure_pipeline_group(constants.DRUPAL_PIPELINE_GROUP_NAME) \
        .ensure_replacement_of_pipeline('rollback-stage-marketing-site') \
        .ensure_material(TUBULAR()) \
        .ensure_material(EDX_MKTG()) \
        .ensure_material(ECOM_SECURE()) \
        .ensure_material(PipelineMaterial(constants.DEPLOY_MARKETING_PIPELINE_NAME, constants.FETCH_TAG_STAGE_NAME))

    pipeline.ensure_environment_variables(
        {
            'MARKETING_REPOSITORY_VERSION': config['mktg_repository_version'],
        }
    )

    pipeline.ensure_encrypted_environment_variables(
        {
            'PRIVATE_GITHUB_KEY': config['github_private_key'],
            'PRIVATE_ACQUIA_USERNAME': config['acquia_username'],
            'PRIVATE_ACQUIA_PASSWORD': config['acquia_password'],
            'PRIVATE_ACQUIA_GITHUB_KEY': config['acquia_github_key'],
        }
    )

    stage_tag_name_artifact_params = {
        'pipeline': constants.DEPLOY_MARKETING_PIPELINE_NAME,
        'stage': constants.FETCH_TAG_STAGE_NAME,
        'job': constants.FETCH_TAG_JOB_NAME,
        'src': FetchArtifactFile('{stage_tag}.txt'.format(stage_tag=constants.STAGE_TAG_NAME)),
        'dest': 'target'
    }

    # Stage to rollback stage to its last stable tag
    rollback_stage = pipeline.ensure_stage(constants.ROLLBACK_STAGE_NAME)
    rollback_stage.set_has_manual_approval()
    rollback_job = rollback_stage.ensure_job(constants.ROLLBACK_JOB_NAME)

    tasks.generate_package_install(rollback_job, 'tubular')
    tasks.generate_target_directory(rollback_job)
    rollback_job.add_task(FetchArtifactTask(**stage_tag_name_artifact_params))
    tasks.generate_drupal_deploy(
        rollback_job,
        constants.STAGE_ENV,
        '{stage_tag}.txt'.format(stage_tag=constants.STAGE_TAG_NAME)
    )

    # Stage to clear the caches
    clear_stage_caches_stage = pipeline.ensure_stage(constants.CLEAR_STAGE_CACHES_STAGE_NAME)
    clear_stage_caches_job = clear_stage_caches_stage.ensure_job(constants.CLEAR_STAGE_CACHES_JOB_NAME)

    tasks.generate_package_install(clear_stage_caches_job, 'tubular')
    clear_stage_caches_job.add_task(
        tasks.bash_task(
            'cp {ecom_secure}/acquia/acquia_github_key.pem {edx_mktg}/docroot/',
            ecom_secure=ECOM_SECURE().destination_directory,
            edx_mktg=EDX_MKTG().destination_directory
        )
    )
    tasks.generate_flush_drupal_caches(clear_stage_caches_job, constants.STAGE_ENV)
    tasks.generate_clear_varnish_cache(clear_stage_caches_job, constants.STAGE_ENV)


if __name__ == '__main__':
    pipeline_script(install_pipelines)
