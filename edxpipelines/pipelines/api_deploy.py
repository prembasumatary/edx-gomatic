#!/usr/bin/env python
"""
Script to build pipelines deploy the edX api gateway.
"""

import sys
from os import path

from gomatic import (
    PipelineMaterial, Tab, BuildArtifact, FetchArtifactFile, FetchArtifactTask,
    FetchArtifactDir, ExecTask
)

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

# pylint: disable=wrong-import-position
from edxpipelines.pipelines import api_build
from edxpipelines import constants
from edxpipelines.pipelines.script import pipeline_script


def install_pipelines(configurator, config):
    """
    Install the pipelines that can deploy the edX api-gateway.
    """
    pipeline = configurator \
        .ensure_pipeline_group(config['pipeline']['group']) \
        .ensure_replacement_of_pipeline(config['pipeline']['name']) \
        .set_label_template('${build}') \
        .set_automatic_pipeline_locking()

    # Allow for a multi-stage deployment
    if 'previous_deployment' in config['upstream_pipelines']:
        build_material = {
            'pipeline': config['upstream_pipelines']['previous_deployment'],
            'stage': 'forward_build',
            'jobs': {
                'swagger': 'forward_build',
                'source': 'forward_build'
            }
        }

    elif 'build' in config['upstream_pipelines']:
        build_material = {
            'pipeline': config['upstream_pipelines']['build'],
            'stage': api_build.BUILD_STAGE_NAME,
            'jobs': {
                'swagger': 'swagger-flatten',
                'source': 'package-source'
            }
        }

    else:
        build_material = {
            'pipeline': config['pipeline']['build'],
            'stage': api_build.BUILD_STAGE_NAME,
            'jobs': {
                'swagger': 'swagger-flatten',
                'source': 'package-source'
            }
        }

    pipeline.ensure_material(PipelineMaterial(build_material['pipeline'], build_material['stage'], 'build'))

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
            'CATALOG_HOST': config['upstream_origins']['catalog'],
            'WAIT_SLEEP_TIME': config.get('tubular_sleep_wait_time', constants.TUBULAR_SLEEP_WAIT_TIME),
        }
    )

    pipeline.ensure_encrypted_environment_variables({
        'AWS_ACCESS_KEY_ID': config['aws']['access_key_id'],
        'AWS_SECRET_ACCESS_KEY': config['aws']['secret_access_key']
    })

    # Setup the Upload stage
    upload_stage = pipeline.ensure_stage('upload').set_clean_working_dir()

    upload_gateway_job = upload_stage.ensure_job('upload_gateway')
    upload_gateway_job.ensure_tab(Tab('output.txt', 'output.txt'))
    upload_gateway_job.ensure_tab(Tab('next_stage.txt', 'next_stage.txt'))

    upload_gateway_job.ensure_artifacts({BuildArtifact('next_stage.txt')})

    swagger_flatten_artifact_params = {
        'pipeline': build_material['pipeline'],
        'stage': build_material['stage'],
        'job': build_material['jobs']['swagger'],
        'src': FetchArtifactFile('swagger.json')
    }
    upload_gateway_job.add_task(FetchArtifactTask(**swagger_flatten_artifact_params))

    api_manager_artifact_params = {
        'pipeline': build_material['pipeline'],
        'stage': build_material['stage'],
        'job': build_material['jobs']['source'],
        'src': FetchArtifactDir('api-manager')
    }
    upload_gateway_job.add_task(FetchArtifactTask(**api_manager_artifact_params))

    upload_gateway_job.add_task(
        ExecTask(
            [
                '/bin/bash', '-c',
                'PYTHONPATH=python-libs python scripts/aws/deploy.py --api-base-domain ${API_BASE} '
                '--swagger-filename ../swagger.json --tag ${GO_PIPELINE_LABEL} --rotation-order '
                '${ROTATION_ORDER} --log-level ${LOG_LEVEL} --metrics ${METRICS} --rate-limit ${RATE_LIMIT} '
                '--burst-limit ${BURST_LIMIT} --edxapp-host ${EDXAPP_HOST} --catalog-host ${CATALOG_HOST} '
                '--landing-page ${ROOT_REDIRECT} > ../next_stage.txt'
            ],
            working_dir='api-manager'
        )
    )

    # Setup the test stage
    test_stage = pipeline.ensure_stage('test')
    test_job = test_stage.ensure_job('test_job')
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
    deploy_stage = pipeline.ensure_stage('deploy')

    if config.get('manual_approval_required', False):
        deploy_stage.set_has_manual_approval()

    deploy_gateway_job = deploy_stage.ensure_job('deploy_gateway')
    deploy_gateway_job.ensure_tab(Tab('output.txt', 'output.txt'))

    deploy_gateway_job.add_task(FetchArtifactTask(
        pipeline.name, 'upload', 'upload_gateway', FetchArtifactFile('next_stage.txt')
    ))
    deploy_gateway_job.add_task(FetchArtifactTask(**api_manager_artifact_params))
    deploy_gateway_job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                'PYTHONPATH=python-libs python scripts/aws/flip.py --api-base-domain ${API_BASE} '
                '--next-stage `cat ../next_stage.txt`'
            ],
            working_dir='api-manager'
        )
    )

    # Setup the Log stage
    log_stage = pipeline.ensure_stage('log')
    log_gateway_job = log_stage.ensure_job('deploy_lambda')

    log_gateway_job.ensure_environment_variables(
        {
            'splunk_host': config['log_lambda']['splunk_host'],
            'subnet_list': config['log_lambda']['subnet_list'],
            'sg_list': config['log_lambda']['sg_list'],
            'environment': config['log_lambda']['environment'],
            'deployment': config['log_lambda']['deployment'],
        }
    )
    log_gateway_job.ensure_encrypted_environment_variables(
        {
            'splunk_token': config['log_lambda']['splunk_token'],
            'acct_id': config['log_lambda']['acct_id'],
            'kms_key': config['log_lambda']['kms_key'],
        }
    )

    log_gateway_job.add_task(FetchArtifactTask(**api_manager_artifact_params))

    log_gateway_job.add_task(
        ExecTask(
            [
                '/bin/bash', '-c',
                'PYTHONPATH=python-libs python scripts/aws/monitor.py --api-base-domain ${API_BASE} '
                '--splunk-host ${splunk_host} --splunk-token ${splunk_token} --acct-id ${acct_id} '
                '--kms-key ${kms_key} --subnet-list ${subnet_list} --sg-list ${sg_list} --environment '
                '${environment} --deployment ${deployment}'
            ],
            working_dir='api-manager'
        )
    )

    # Setup the forward_build stage (which makes the build available to the next pipeline)
    forward_build_stage = pipeline.ensure_stage('forward_build')
    forward_build_job = forward_build_stage.ensure_job('forward_build')
    forward_build_job.add_task(FetchArtifactTask(**api_manager_artifact_params))
    forward_build_job.add_task(FetchArtifactTask(**swagger_flatten_artifact_params))
    forward_build_job.ensure_artifacts(set([BuildArtifact("api-manager"), BuildArtifact("swagger.json")]))


if __name__ == '__main__':
    pipeline_script(install_pipelines)
