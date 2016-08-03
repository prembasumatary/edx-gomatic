#!/usr/bin/env python
import sys
from os import path
import click
from gomatic import *

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

import edxpipelines.utils as utils
import edxpipelines.patterns.tasks as tasks
from edxpipelines.constants import *


@click.command()
@click.option('--save-config', 'save_config_locally', envvar='SAVE_CONFIG',
              help='Save the pipeline configuration xml locally', required=False, default=False)
@click.option('--dry-run', envvar='DRY_RUN',
              help='do a dry run of  the pipeline installation, and save the pre/post xml configurations locally',
              required=False, default=False)
@click.option('--variable_file', 'variable_files', multiple=True,
              help='path to yaml variable file with a dictionary of key/value pairs to be used as variables in the script',
              required=False, default=[])
@click.option('-e', '--variable', 'cmd_line_vars', multiple=True,
              help='key/value of a variable used as a replacement in this script', required=False, type=(str, str),
              nargs=2, default={})
def install_pipeline(save_config_locally, dry_run, variable_files, cmd_line_vars):
    config = utils.merge_files_and_dicts(variable_files, list(cmd_line_vars, ))

    configurator = GoCdConfigurator(
        HostRestClient(config['gocd_url'], config['gocd_username'], config['gocd_password'], ssl=True))

    pipeline = configurator \
        .ensure_pipeline_group('Deploy') \
        .ensure_replacement_of_pipeline('rollback-prod-marketing-site') \
        .set_git_material(GitMaterial('https://github.com/edx/tubular', polling=False, destination_directory='tubular')) \
        .ensure_material(PipelineMaterial(DEPLOY_MARKETING_PIPELINE_NAME, FETCH_TAG_STAGE_NAME))

    pipeline.ensure_environment_variables(
        {
            'MARKETING_REPOSITORY_VERSION': 'ddumesnil/Drush',
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

    # Stage to clear caches in extra
    clear_prod_caches_stage = pipeline.ensure_stage(CLEAR_PROD_CACHES_STAGE_NAME)
    clear_prod_caches_stage.set_has_manual_approval()
    clear_prod_caches_job = clear_prod_caches_stage.ensure_job(CLEAR_PROD_CACHES_JOB_NAME)

    tasks.fetch_edx_mktg(clear_prod_caches_job, 'edx-mktg')
    tasks.generate_requirements_install(clear_prod_caches_job, 'tubular')
    tasks.format_RSA_key(clear_prod_caches_job, 'edx-mktg/docroot/acquia_github_key.pem', '$PRIVATE_ACQUIA_GITHUB_KEY')
    tasks.generate_flush_drupal_caches(clear_prod_caches_job, PROD_ENV)
    tasks.generate_clear_varnish_cache(clear_prod_caches_job, PROD_ENV)

    prod_tag_name_artifact_params = {
        'pipeline': DEPLOY_MARKETING_PIPELINE_NAME,
        'stage': FETCH_TAG_STAGE_NAME,
        'job': FETCH_TAG_JOB_NAME,
        'src': FetchArtifactFile('{prod_tag}.txt'.format(prod_tag=PROD_TAG_NAME)),
        'dest': 'target'
    }

    # Stage to rollback stage to its last stable tag
    rollback_stage = pipeline.ensure_stage(ROLLBACK_STAGE_NAME)
    rollback_job = rollback_stage.ensure_job(ROLLBACK_JOB_NAME)

    tasks.generate_requirements_install(rollback_job, 'tubular')
    tasks.generate_target_directory(rollback_job)
    rollback_job.add_task(FetchArtifactTask(**prod_tag_name_artifact_params))
    tasks.generate_drupal_deploy(rollback_job, PROD_ENV, '{prod_tag}.txt'.format(prod_tag=PROD_TAG_NAME))

    configurator.save_updated_config(save_config_locally=save_config_locally, dry_run=dry_run)


if __name__ == '__main__':
    install_pipeline()
