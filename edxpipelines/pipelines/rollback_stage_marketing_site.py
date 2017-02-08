#!/usr/bin/env python
import sys
from os import path
import click
from gomatic import *

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

from edxpipelines import utils
from edxpipelines import constants
from edxpipelines.patterns import tasks
from edxpipelines.constants import *
from edxpipelines.pipelines.script import pipeline_script


def install_pipelines(configurator, config, env_configs):

    pipeline = configurator \
        .ensure_pipeline_group(DRUPAL_PIPELINE_GROUP_NAME) \
        .ensure_replacement_of_pipeline('rollback-stage-marketing-site') \
        .set_git_material(GitMaterial('https://github.com/edx/tubular',
                                      polling=True,
                                      destination_directory='tubular',
                                      ignore_patterns=constants.MATERIAL_IGNORE_ALL_REGEX
                                      )
                          ) \
        .ensure_material(PipelineMaterial(DEPLOY_MARKETING_PIPELINE_NAME, FETCH_TAG_STAGE_NAME))

    pipeline.ensure_environment_variables(
        {
            'MARKETING_REPOSITORY_VERSION': config['mktg_repository_version'],
        }
    )

    pipeline.ensure_encrypted_environment_variables(
        {
            'PRIVATE_GITHUB_KEY': config['github_private_key'],
            'PRIVATE_MARKETING_REPOSITORY_URL': config['mktg_repository_url'],
            'PRIVATE_ACQUIA_USERNAME': config['acquia_username'],
            'PRIVATE_ACQUIA_PASSWORD': config['acquia_password'],
            'PRIVATE_ACQUIA_GITHUB_KEY': config['acquia_github_key'],
        }
    )

    stage_tag_name_artifact_params = {
        'pipeline': DEPLOY_MARKETING_PIPELINE_NAME,
        'stage': FETCH_TAG_STAGE_NAME,
        'job': FETCH_TAG_JOB_NAME,
        'src': FetchArtifactFile('{stage_tag}.txt'.format(stage_tag=STAGE_TAG_NAME)),
        'dest': 'target'
    }

    # Stage to rollback stage to its last stable tag
    rollback_stage = pipeline.ensure_stage(ROLLBACK_STAGE_NAME)
    rollback_stage.set_has_manual_approval()
    rollback_job = rollback_stage.ensure_job(ROLLBACK_JOB_NAME)

    tasks.generate_requirements_install(rollback_job, 'tubular')
    tasks.generate_target_directory(rollback_job)
    rollback_job.add_task(FetchArtifactTask(**stage_tag_name_artifact_params))
    tasks.generate_drupal_deploy(rollback_job, STAGE_ENV, '{stage_tag}.txt'.format(stage_tag=STAGE_TAG_NAME))

    # Stage to clear the caches
    clear_stage_caches_stage = pipeline.ensure_stage(CLEAR_STAGE_CACHES_STAGE_NAME)
    clear_stage_caches_job = clear_stage_caches_stage.ensure_job(CLEAR_STAGE_CACHES_JOB_NAME)

    tasks.fetch_edx_mktg(clear_stage_caches_job, 'edx-mktg')
    tasks.generate_requirements_install(clear_stage_caches_job, 'tubular')
    tasks.format_RSA_key(clear_stage_caches_job, '../edx-mktg/docroot/acquia_github_key.pem', '$PRIVATE_ACQUIA_GITHUB_KEY')
    tasks.generate_flush_drupal_caches(clear_stage_caches_job, STAGE_ENV)
    tasks.generate_clear_varnish_cache(clear_stage_caches_job, STAGE_ENV)


if __name__ == '__main__':
    pipeline_script(install_pipelines)
