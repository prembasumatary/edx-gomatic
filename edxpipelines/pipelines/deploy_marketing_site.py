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
        .ensure_replacement_of_pipeline(DEPLOY_MARKETING_PIPELINE_NAME) \
        .set_git_material(GitMaterial('https://github.com/edx/tubular',
                                      polling=True,
                                      destination_directory='tubular',
                                      ignore_patterns=constants.MATERIAL_IGNORE_ALL_REGEX
                                      )
                          )

    pipeline.ensure_environment_variables(
        {
            'MARKETING_REPOSITORY_VERSION': config['mktg_repository_version'],
        }
    )

    pipeline.ensure_encrypted_environment_variables(
        {
            'PRIVATE_GITHUB_KEY': config['github_private_key'],
            'PRIVATE_MARKETING_REPOSITORY_URL': config['mktg_repository_url'],
            'PRIVATE_ACQUIA_REMOTE': config['acquia_remote_url'],
            'PRIVATE_ACQUIA_USERNAME': config['acquia_username'],
            'PRIVATE_ACQUIA_PASSWORD': config['acquia_password'],
            'PRIVATE_ACQUIA_GITHUB_KEY': config['acquia_github_key']
        }
    )

    # Stage to fetch the current tag names from stage and prod
    fetch_tag_stage = pipeline.ensure_stage(FETCH_TAG_STAGE_NAME)
    fetch_tag_stage.set_has_manual_approval()
    fetch_tag_job = fetch_tag_stage.ensure_job(FETCH_TAG_JOB_NAME)
    tasks.generate_requirements_install(fetch_tag_job, 'tubular')
    tasks.generate_target_directory(fetch_tag_job)
    path_name = '../target/{env}_tag_name.txt'
    tasks.generate_fetch_tag(fetch_tag_job, STAGE_ENV, path_name)
    tasks.generate_fetch_tag(fetch_tag_job, PROD_ENV, path_name)

    fetch_tag_job.ensure_artifacts(
        set([BuildArtifact('target/{stage_tag}.txt'.format(stage_tag=STAGE_TAG_NAME)),
             BuildArtifact('target/{prod_tag}.txt'.format(prod_tag=PROD_TAG_NAME))])
    )

    # Stage to create and push a tag to Acquia.
    push_to_acquia_stage = pipeline.ensure_stage(PUSH_TO_ACQUIA_STAGE_NAME)
    push_to_acquia_job = push_to_acquia_stage.ensure_job(PUSH_TO_ACQUIA_JOB_NAME)
    # Ensures the tag name is accessible in future jobs.
    push_to_acquia_job.ensure_artifacts(
        set([BuildArtifact('target/{new_tag}.txt'.format(new_tag=NEW_TAG_NAME))])
    )

    tasks.generate_requirements_install(push_to_acquia_job, 'tubular')
    tasks.generate_target_directory(push_to_acquia_job)
    tasks.fetch_edx_mktg(push_to_acquia_job, 'edx-mktg')

    # Create a tag from MARKETING_REPOSITORY_VERSION branch of marketing repo
    push_to_acquia_job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                # Writing dates to a file should help with any issues dealing with a job
                # taking place over two days (23:59:59 -> 00:00:00). Only the day can be
                # affected since we don't use minutes or seconds.
                # NOTE: Uses UTC
                'echo -n "release-$(date +%Y-%m-%d-%H.%M)" > ../target/{new_tag}.txt && '
                'TAG_NAME=$(cat ../target/{new_tag}.txt) && '
                '/usr/bin/git config user.email "admin@edx.org" && '
                '/usr/bin/git config user.name "edx-secure" && '
                '/usr/bin/git tag -a $TAG_NAME -m "Release for $(date +%B\ %d,\ %Y). Created by $GO_TRIGGER_USER." && '
                'GIT_SSH_COMMAND="/usr/bin/ssh -o StrictHostKeyChecking=no -i ../github_key.pem" '
                '/usr/bin/git push origin $TAG_NAME'.format(new_tag=NEW_TAG_NAME)
            ],
            working_dir='edx-mktg'
        )
    )

    # Set up Acquia Github key for use in pushing tag to Acquia
    tasks.format_RSA_key(push_to_acquia_job, '../acquia_github_key.pem', '$PRIVATE_ACQUIA_GITHUB_KEY')

    # Set up Acquia remote repo and push tag to Acquia. Change new tag file to contain "tags/" for deployment.
    push_to_acquia_job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                '/usr/bin/git remote add acquia $PRIVATE_ACQUIA_REMOTE && '
                'GIT_SSH_COMMAND="/usr/bin/ssh -o StrictHostKeyChecking=no -i ../acquia_github_key.pem" '
                '/usr/bin/git push acquia $(cat ../target/{new_tag}.txt) && '
                'echo -n "tags/" | cat - ../target/{new_tag}.txt > temp && mv temp ../target/{new_tag}.txt'.format(new_tag=NEW_TAG_NAME)
            ],
            working_dir='edx-mktg'
        )
    )

    # Stage to backup database in stage
    backup_stage_database_stage = pipeline.ensure_stage(BACKUP_STAGE_DATABASE_STAGE_NAME)
    backup_stage_database_job = backup_stage_database_stage.ensure_job(BACKUP_STAGE_DATABASE_JOB_NAME)

    tasks.generate_requirements_install(backup_stage_database_job, 'tubular')
    tasks.generate_backup_drupal_database(backup_stage_database_job, STAGE_ENV)

    # Stage to deploy to stage
    deploy_stage_for_stage = pipeline.ensure_stage(DEPLOY_STAGE_STAGE_NAME)
    deploy_job_for_stage = deploy_stage_for_stage.ensure_job(DEPLOY_STAGE_JOB_NAME)

    tasks.generate_requirements_install(deploy_job_for_stage, 'tubular')
    tasks.generate_target_directory(deploy_job_for_stage)

    # fetch the tag name
    new_tag_name_artifact_params = {
        'pipeline': DEPLOY_MARKETING_PIPELINE_NAME,
        'stage': PUSH_TO_ACQUIA_STAGE_NAME,
        'job': PUSH_TO_ACQUIA_JOB_NAME,
        'src': FetchArtifactFile('{new_tag}.txt'.format(new_tag=NEW_TAG_NAME)),
        'dest': 'target'
    }
    deploy_job_for_stage.add_task(FetchArtifactTask(**new_tag_name_artifact_params))
    tasks.generate_drupal_deploy(deploy_job_for_stage, STAGE_ENV, '{new_tag}.txt'.format(new_tag=NEW_TAG_NAME))

    # Stage to clear caches in stage
    clear_stage_caches_stage = pipeline.ensure_stage(CLEAR_STAGE_CACHES_STAGE_NAME)
    clear_stage_caches_job = clear_stage_caches_stage.ensure_job(CLEAR_STAGE_CACHES_JOB_NAME)

    tasks.fetch_edx_mktg(clear_stage_caches_job, 'edx-mktg')
    tasks.generate_requirements_install(clear_stage_caches_job, 'tubular')
    tasks.format_RSA_key(clear_stage_caches_job, '../edx-mktg/docroot/acquia_github_key.pem', '$PRIVATE_ACQUIA_GITHUB_KEY')
    tasks.generate_flush_drupal_caches(clear_stage_caches_job, STAGE_ENV)
    tasks.generate_clear_varnish_cache(clear_stage_caches_job, STAGE_ENV)

    # Stage to backup database in prod
    backup_prod_database_stage = pipeline.ensure_stage(BACKUP_PROD_DATABASE_STAGE_NAME)
    backup_prod_database_stage.set_has_manual_approval()
    backup_prod_database_job = backup_prod_database_stage.ensure_job(BACKUP_PROD_DATABASE_JOB_NAME)

    tasks.generate_requirements_install(backup_prod_database_job, 'tubular')
    tasks.generate_backup_drupal_database(backup_prod_database_job, PROD_ENV)

    # Stage to deploy to prod
    deploy_stage_for_prod = pipeline.ensure_stage(DEPLOY_PROD_STAGE_NAME)
    deploy_job_for_prod = deploy_stage_for_prod.ensure_job(DEPLOY_PROD_JOB_NAME)

    tasks.generate_requirements_install(deploy_job_for_prod, 'tubular')
    tasks.generate_target_directory(deploy_job_for_prod)
    deploy_job_for_prod.add_task(FetchArtifactTask(**new_tag_name_artifact_params))
    tasks.generate_drupal_deploy(deploy_job_for_prod, PROD_ENV, '{new_tag}.txt'.format(new_tag=NEW_TAG_NAME))

    # Stage to clear caches in prod
    clear_prod_caches_stage = pipeline.ensure_stage(CLEAR_PROD_CACHES_STAGE_NAME)
    clear_prod_caches_job = clear_prod_caches_stage.ensure_job(CLEAR_PROD_CACHES_JOB_NAME)

    tasks.fetch_edx_mktg(clear_prod_caches_job, 'edx-mktg')
    tasks.generate_requirements_install(clear_prod_caches_job, 'tubular')
    tasks.format_RSA_key(clear_prod_caches_job, '../edx-mktg/docroot/acquia_github_key.pem', '$PRIVATE_ACQUIA_GITHUB_KEY')
    tasks.generate_flush_drupal_caches(clear_prod_caches_job, PROD_ENV)
    tasks.generate_clear_varnish_cache(clear_prod_caches_job, PROD_ENV)


if __name__ == '__main__':
    pipeline_script(install_pipelines)
