#!/usr/bin/env python

from gomatic import *
from edxpipelines.templates import stages

import click
import edxpipelines.utils as utils



@click.command()
@click.option('--save-config', 'save_config_locally', envvar='SAVE_CONFIG', help='Save the pipeline configuration xml locally', required=False, default=False)
@click.option('--dry-run', envvar='DRY_RUN', help='do a dry run of  the pipeline installation, and save the pre/post xml configurations locally', required=False, default=False)
@click.option('--variable_file', 'variable_files', multiple=True, help='path to yaml variable file with a dictionary of key/value pairs to be used as variables in the script', required=False)
@click.option('-e', '--variable', 'cmd_line_vars', multiple=True, help='key/value of a variable used as a replacement in this script', required=False, type=(str, str), nargs=2)
def install_pipeline(save_config_locally, dry_run, variable_files=[], cmd_line_vars={}):
    """
    Variables needed for this pipeline:
    - gocd_username
    - gocd_password
    - gocd_url
    - pipeline_group
    - pipeline_name
    - asgard_api_endpoints
    - asgard_token
    - aws_access_key_id
    - aws_secret_access_key
    - cron_timer
    """

    config = utils.merge_files_and_dicts(variable_files, cmd_line_vars)
    
    configurator = GoCdConfigurator(HostRestClient(config['gocd_username'], config['gocd_username'], config['gocd_password'], ssl=True))

    pipeline = configurator.ensure_pipeline_group(config['pipline_group'])\
    	                   .ensure_replacement_of_pipeline(config['pipeline_name'])\
    	                   .set_timer(config['cron_timer'])\
    	                   .set_git_material(GitMaterial("https://github.com/edx/tubular.git", polling=False, destination_directory="tubular"))

    stages.generate_asg_cleanup(pipeline, config['asgard_api_endpoints'], config['asgard_token'], config['aws_access_key_id'], config['aws_secret_access_key'])
    configurator.save_updated_config(save_config_locally=save_config_locally, dry_run=dry_run)

if __name__ == "__main__":
    install_pipeline()
