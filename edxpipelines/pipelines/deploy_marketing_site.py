#!/usr/bin/env python

from gomatic import *

import click
import edxpipelines.utils as utils
import edxpipelines.patterns.stages as stages
import edxpipelines.patterns.tasks as tasks


@click.command()
@click.option('--save-config', 'save_config_locally', envvar='SAVE_CONFIG',
              help='Save the pipeline configuration xml locally', required=False, default=False)
@click.option('--dry-run', envvar='DRY_RUN',
              help='do a dry run of  the pipeline installation, and save the pre/post xml configurations locally',
              required=False, default=False)
@click.option('--variable_file', 'variable_files', multiple=True,
              help='path to yaml variable file with a dictionary of key/value pairs to be used as variables in the script',
              required=False, default = [])
@click.option('-e', '--variable', 'cmd_line_vars', multiple=True,
              help='key/value of a variable used as a replacement in this script', required=False, type=(str, str),
              nargs=2, default = {})
def install_pipeline(save_config_locally, dry_run, variable_files, cmd_line_vars):
    config = utils.merge_files_and_dicts(variable_files, list(cmd_line_vars, ))

    configurator = GoCdConfigurator(
        HostRestClient(config['gocd_username'], config['gocd_username'], config['gocd_password'], ssl=True))

    pipeline = configurator \
        .ensure_pipeline_group("marketing_deployment") \
        .ensure_replacement_of_pipeline("marketing_deployment") \
        .set_git_material(GitMaterial("https://github.com/edx/tubular", polling=False))

    # Stage to push to drupal
    # tasks:
    # - Checkout and pull the master branch of marketing repo
    # - Create a tag
    # - Set up Acquia remote repo
    # - Push the tag to Acquia
    # after checkout and pull, the rest of this could be written as a single task
    push_to_drupal_stage = pipeline.ensure_stage("github_workflow")
    push_to_drupal_job = push_to_drupal_stage.ensure_job("push_to_drupal_job")
    pipeline.ensure_environment_variables(
        {
            'PRIVATE_GITHUB_KEY': config['private_github_key'],
            'PRIVATE_REPOSITORY_URL': config['mktg_repository_url'],  # I dunno, you pick the name, mktg_repository_url will go in a <config>.yml file that you feed this script
            'PRIVATE_REPOSITORY_version': config['mktg_repository_version'], # this can be overridden by the person running the pipeline when they click play + on the UI
            # Any further variables you need inside this stage to push to aquia should go here, you'll also need the url for the aquia remote
         }
    )
    tasks.generate_fetch_secure_repository(push_to_drupal_job, 'edx-marketing') # modified this pattern for you so it will work with all secure repositories.

    # Dillon Since you need to clear the caches twice you should make these in to patterns. Call once for stage, once for prod. Examples here are to get yoru started on the concepts
    # Stage to clear caches
    clear_caches_stage = pipeline.ensure_stage("clear_drupal_caches")
    clear_caches_job = clear_caches_stage.ensure_job('clear_drupal_caches_job')
    tasks.generate_requirements_install(clear_caches_job, 'tubular')
    # TODO write the task to clear the cache
    # clear_caches_job.add_task(
    #     ExecTask(
    #         [
    #             '/bin/bash',
    #             '-c',
    #             'drush blah blah && '
    #             'drush blah blah '
    #         ],
    #         working_dir='tubular/'
    #     )
    # )

    # Stage to deploy
    deploy_stage = pipeline.ensure_stage("deploy_drupal")
    deploy_job = deploy_stage.ensure_job('deploy_drupal_job')
    tasks.generate_requirements_install(deploy_job, 'tubular')
    # TODO write the bash that will call your tubular script that calls the aquia api to release the codes
    # deploy_job.add_task(
    #     ExecTask(
    #         [
    #             '/bin/bash',
    #             '-c',
    #             'python scripts/your_script.py --arg my_arg '
    #         ],
    #         working_dir='tubular/'
    #     )
    # )

    configurator.save_updated_config(save_config_locally=save_config_locally, dry_run=dry_run)


if __name__ == "__main__":
    install_pipeline()