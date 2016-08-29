#!/usr/bin/env python

from gomatic import *

import click

import sys
from os import path

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

import edxpipelines.utils as utils
import edxpipelines.pipelines.api_build as api_build

UPLOAD_STAGE_NAME = 'upload'
UPLOAD_GATEWAY_JOB_NAME = 'upload_gateway'
TEST_STAGE_NAME = 'test'
TEST_JOB_NAME = 'test_job'
DEPLOY_STAGE_NAME = 'deploy'
DEPLOY_GATEWAY_JOB_NAME = 'deploy_gateway'
LOG_STAGE_NAME = 'log'
LOG_JOB_NAME = 'deploy_lambda'


@click.command()
@click.option('--save-config',
              'save_config_locally',
              envvar='SAVE_CONFIG',
              help='Save the pipeline configuration xml locally',
              required=False,
              default=False)
@click.option('--dry-run',
              envvar='DRY_RUN',
              help='do a dry run of  the pipeline installation, and save the pre/post xml configurations locally',
              required=False,
              default=False,
              is_flag=True)
@click.option('--variable_file',
              'variable_files',
              multiple=True,
              help='path to yaml variable file with a dictionary of key/value pairs to be used as variables in the script',
              required=False,
              default=[])
@click.option('-e',
              '--variable',
              'cmd_line_vars',
              multiple=True,
              help='key/value of a variable used as a replacement in this script',
              required=False,
              type=(str, str),
              nargs=2,
              default={})
def install_pipeline(save_config_locally, dry_run, variable_files, cmd_line_vars):
    config = utils.merge_files_and_dicts(variable_files, list(cmd_line_vars, ))

    configurator = GoCdConfigurator(HostRestClient(config['gocd_url'],
                                                   config['gocd_username'],
                                                   config['gocd_password'],
                                                   ssl=True))

    pipeline = configurator \
        .ensure_pipeline_group(config['pipeline']['group']) \
        .ensure_replacement_of_pipeline(config['pipeline']['name']) \
        .set_label_template('${build}') \
        .set_automatic_pipeline_locking()

    pipeline.ensure_material(PipelineMaterial(config['pipeline']['build'], api_build.BUILD_STAGE_NAME, 'build'))

    pipeline.ensure_environment_variables(
        {
            'ROOT_REDIRECT': config['root_redirect'],
            'API_BASE': config['api_base'],
            'LOG_LEVEL': config['aws']['log_level'],
            'RATE_LIMIT': config['aws']['rate_limit'],
            'METRICS': config['aws']['metrics'],
            'ROTATION_ORDER': ' '.join(config['rotation_order']),
            'BURST_LIMIT': config['aws']['burst_limit'],
            'EDXAPP_HOST': config['upstream_origins']['edxapp'],
            'CATALOG_HOST': config['upstream_origins']['catalog']
        }
    )
    pipeline.ensure_encrypted_environment_variables({
        'AWS_ACCESS_KEY_ID': config['aws']['access_key_id'],
        'AWS_SECRET_ACCESS_KEY': config['aws']['secret_access_key']
    })

    # Setup the Upload stage
    upload_stage = pipeline.ensure_stage(UPLOAD_STAGE_NAME).set_clean_working_dir()

    if config.get('manual_approval_required', False):
        upload_stage.set_has_manual_approval()

    upload_gateway_job = upload_stage.ensure_job(UPLOAD_GATEWAY_JOB_NAME)
    upload_gateway_job.ensure_tab(Tab('output.txt', 'output.txt'))
    upload_gateway_job.ensure_tab(Tab('next_stage.txt', 'next_stage.txt'))

    upload_gateway_job.ensure_artifacts({BuildArtifact('next_stage.txt')})

    swagger_flatten_artifact_params = {
        'pipeline': config['pipeline']['build'],
        'stage': api_build.BUILD_STAGE_NAME,
        'job': api_build.SWAGGER_FLATTEN_JOB_NAME,
        'src': FetchArtifactFile('swagger.json')
    }
    upload_gateway_job.add_task(FetchArtifactTask(**swagger_flatten_artifact_params))

    api_manager_artifact_params = {
        'pipeline': config['pipeline']['build'],
        'stage': api_build.BUILD_STAGE_NAME,
        'job': api_build.PACKAGE_SOURCE_JOB_NAME,
        'src': FetchArtifactDir(api_build.API_MANAGER_WORKING_DIR)
    }
    upload_gateway_job.add_task(FetchArtifactTask(**api_manager_artifact_params))

    upload_gateway_job.add_task(
        ExecTask(
            [
                '/bin/bash', '-c',
                'PYTHONPATH=python-libs python scripts/aws/deploy.py --api-base-domain ${API_BASE} --swagger-filename ../swagger.json --tag ${GO_PIPELINE_LABEL} --rotation-order ${ROTATION_ORDER} --log-level ${LOG_LEVEL} --metrics ${METRICS} --rate-limit ${RATE_LIMIT} --burst-limit ${BURST_LIMIT} --edxapp-host ${EDXAPP_HOST} --catalog-host ${CATALOG_HOST} --landing-page ${ROOT_REDIRECT} > ../next_stage.txt'
            ],
            working_dir='api-manager'
        )
    )

    # Setup the test stage
    test_stage = pipeline.ensure_stage(TEST_STAGE_NAME)
    test_job = test_stage.ensure_job(TEST_JOB_NAME)
    test_job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                '/bin/echo "need to implement these tests, just stubbing out the stage for now"'
            ]
        )
    )

    # Setup the deploy stage
    deploy_stage = pipeline.ensure_stage(DEPLOY_STAGE_NAME)
    deploy_gateway_job = deploy_stage.ensure_job(DEPLOY_GATEWAY_JOB_NAME)
    deploy_gateway_job.ensure_tab(Tab('output.txt', 'output.txt'))

    next_stage_artifact_params = {
        'pipeline': pipeline.name,
        'stage': UPLOAD_STAGE_NAME,
        'job': UPLOAD_GATEWAY_JOB_NAME,
        'src': FetchArtifactFile('next_stage.txt')
    }
    deploy_gateway_job.add_task(FetchArtifactTask(**next_stage_artifact_params))
    deploy_gateway_job.add_task(FetchArtifactTask(**api_manager_artifact_params))
    deploy_gateway_job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                'PYTHONPATH=python-libs python scripts/aws/flip.py --api-base-domain ${API_BASE} --next-stage `cat ../next_stage.txt`'
            ],
            working_dir='api-manager'
        )
    )

    # Setup the Log stage
    log_stage = pipeline.ensure_stage(LOG_STAGE_NAME)
    log_gateway_job = log_stage.ensure_job(LOG_JOB_NAME)

    log_gateway_job.ensure_environment_variables(
        {
            'splunk-host': config['log_lambda']['splunk-host'],
            'subnet-list': config['log_lambda']['subnet-list'],
            'sg-list': config['log_lambda']['sg-list'],
            'environment': config['log_lambda']['environment'],
            'deployment': config['log_lambda']['deployment'],
        }
    )
    log_gateway_job.ensure_encrypted_environment_variables(
        {
            'splunk-token': config['log_lambda']['splunk-token'],
            'acct-id': config['log_lambda']['acct-id'],
            'kms-key': config['log_lambda']['kms-key'],
        }
    )

    log_gateway_job.add_task(FetchArtifactTask(**api_manager_artifact_params))

    log_gateway_job.add_task(
        ExecTask(
            [
                '/bin/bash', '-c',
                'PYTHONPATH=python-libs python scripts/aws/monitor.py --api-base-domain ${API_BASE} --splunk-host ${splunk-host} --splunk-token ${splunk-token} --acct-id ${acct-id} --kms-key ${kms-key} --subnet-list ${subnet-list} --sg-list ${sg-list} --environment ${environment} --deployment ${deployment}'
            ],
            working_dir='api-manager'
        )
    )

    configurator.save_updated_config(save_config_locally=save_config_locally, dry_run=dry_run)

if __name__ == '__main__':
    install_pipeline()
