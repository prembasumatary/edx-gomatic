#!/usr/bin/env python

from gomatic import *

import click

import sys
from os import path

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

import edxpipelines.utils as utils


@click.command()
@click.option('--save-config', 'save_config_locally', envvar='SAVE_CONFIG', help='Save the pipeline configuration xml locally', required=False, default=False)
@click.option('--dry-run', envvar='DRY_RUN', help='do a dry run of  the pipeline installation, and save the pre/post xml configurations locally', required=False, default=False, is_flag=True)
@click.option('--variable_file', 'variable_files', multiple=True, help='path to yaml variable file with a dictionary of key/value pairs to be used as variables in the script', required=False, default=[])
@click.option('-e', '--variable', 'cmd_line_vars', multiple=True, help='key/value of a variable used as a replacement in this script', required=False, type=(str, str), nargs=2, default={})
def install_pipeline(save_config_locally, dry_run, variable_files, cmd_line_vars):
    config = utils.merge_files_and_dicts(variable_files, list(cmd_line_vars,))
    
    configurator = GoCdConfigurator(HostRestClient(config['gocd_url'], config['gocd_username'], config['gocd_password'], ssl=True))
    pipeline = configurator\
    	.ensure_pipeline_group(config['pipeline']['group'])\
    	.ensure_replacement_of_pipeline(config['pipeline']['name'])\
    	.set_label_template("${build}")\
    	.set_automatic_pipeline_locking()\
    	.ensure_material(PipelineMaterial(config['pipeline']['build'], "build", "build"))

    pipeline.ensure_environment_variables({
        'ROOT_REDIRECT': config['root_redirect'],
        'API_BASE': config['api_base'],
        'LOG_LEVEL': config['aws']['log_level'],
        'RATE_LIMIT': config['aws']['rate_limit'],
        'METRICS': config['aws']['metrics'],
        'ROTATION_ORDER': ' '.join(config['rotation_order']),
        'BURST_LIMIT': config['aws']['burst_limit'],
        'EDXAPP_HOST': config['upstream_origins']['edxapp'],
        'CATALOG_HOST': config['upstream_origins']['catalog']
    })
    pipeline.ensure_encrypted_environment_variables({
        'AWS_ACCESS_KEY_ID': config['aws']['access_key_id'],
        'AWS_SECRET_ACCESS_KEY': config['aws']['secret_access_key']
    })

    stage = pipeline.ensure_stage("upload").set_clean_working_dir()
    if config['manual_approval_required']:
        stage.set_has_manual_approval()
    job = stage.ensure_job("upload_gateway").ensure_artifacts({BuildArtifact("next_stage.txt")}).ensure_tab(Tab("output.txt", "output.txt")).ensure_tab(Tab("next_stage.txt", "next_stage.txt"))
    job.add_task(FetchArtifactTask(config['pipeline']['build'], "build", "swagger-flatten", FetchArtifactFile("swagger.json")))
    job.add_task(FetchArtifactTask(config['pipeline']['build'], "build", "package-source", FetchArtifactDir("api-manager")))
    job.add_task(ExecTask(['/bin/bash', '-c', 'PYTHONPATH=python-libs python scripts/aws/deploy.py --api-base-domain ${API_BASE} --swagger-filename ../swagger.json --tag ${GO_PIPELINE_LABEL} --rotation-order ${ROTATION_ORDER} --log-level ${LOG_LEVEL} --metrics ${METRICS} --rate-limit ${RATE_LIMIT} --burst-limit ${BURST_LIMIT} --edxapp-host ${EDXAPP_HOST} --catalog-host ${CATALOG_HOST} --landing-page ${ROOT_REDIRECT} > ../next_stage.txt'], working_dir="api-manager"))

    stage = pipeline.ensure_stage("test")
    job = stage.ensure_job("TODO")
    job.add_task(ExecTask(['/bin/bash', '-c', '/bin/echo "need to implement these tests, just stubbing out the stage for now"']))

    stage = pipeline.ensure_stage("deploy")
    job = stage.ensure_job("deploy_gateway").ensure_tab(Tab("output.txt", "output.txt"))
    job.add_task(FetchArtifactTask("", "upload", "upload_gateway", FetchArtifactFile("next_stage.txt")))
    job.add_task(FetchArtifactTask(config['pipeline']['build'], "build", "package-source", FetchArtifactDir("api-manager")))
    job.add_task(ExecTask(['/bin/bash', '-c', 'PYTHONPATH=python-libs python scripts/aws/flip.py --api-base-domain ${API_BASE} --next-stage `cat ../next_stage.txt`'], working_dir="api-manager"))
   
    configurator.save_updated_config(save_config_locally=save_config_locally, dry_run=dry_run)

if __name__ == "__main__":
    install_pipeline()
