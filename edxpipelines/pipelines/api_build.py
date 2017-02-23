#!/usr/bin/env python
"""
Script to install pipelines that can build the edX api-gateway.
"""

import sys
from os import path

from gomatic import GitMaterial, ExecTask, BuildArtifact, FetchArtifactFile, FetchArtifactTask

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

# pylint: disable=wrong-import-position
from edxpipelines.pipelines.script import pipeline_script

SETUP_STAGE_NAME = 'setup'
WAIT_FOR_TRAVIS_JOB_NAME = 'wait-for-travis'
DOWNLOAD_STAGE_NAME = 'download'
SWAGGER_CODEGEN_JOB_NAME = 'swagger-codegen'
SWAGGER_JAR = 'swagger-codegen-cli.jar'
BUILD_STAGE_NAME = 'build'
SWAGGER_FLATTEN_JOB_NAME = 'swagger-flatten'
PACKAGE_SOURCE_JOB_NAME = 'package-source'
API_MANAGER_WORKING_DIR = 'api-manager'


def install_pipelines(configurator, config, env_configs):  # pylint: disable=unused-argument
    """
    Install pipelines that can build the edX api-gateway.
    """
    pipeline = configurator \
        .ensure_pipeline_group(config['pipeline']['group']) \
        .ensure_replacement_of_pipeline(config['pipeline']['name']) \
        .set_label_template('${api-manager}') \
        .set_git_material(GitMaterial(
            config['github']['server_uri'] + '/' + config['github']['repository'],
            branch='#{GIT_BRANCH}',
            destination_directory=API_MANAGER_WORKING_DIR
        ))

    pipeline.ensure_parameters({'GIT_BRANCH': config['github']['branch']})

    pipeline.ensure_environment_variables(
        {
            'SWAGGER_CODEGEN_JAR': config['swagger_codegen_jar'],
            'GITHUB_API_REPO': config['github']['repository'],
            'GITHUB_API_URI': config['github']['api_uri'],
            'GITHUB_API_POLL_WAIT_S': config['github']['api_poll_wait_s'],
            'GITHUB_API_POLL_RETRIES': config['github']['api_poll_retries']
        }
    )

    # Note, need to move this Github poll hack to something less of a hack at some point.
    setup_stage = pipeline.ensure_stage(SETUP_STAGE_NAME)
    wait_for_travis_job = setup_stage.ensure_job(WAIT_FOR_TRAVIS_JOB_NAME)
    # pylint: disable=bad-continuation
    wait_for_travis_job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                'i=0; until python -c "'
                    'import requests; '
                    'assert(requests.get('
                        '\'${GITHUB_API_URI}/${GITHUB_API_REPO}/commits/{}/status\'.format('
                            '\'${GO_REVISION_API_MANAGER}\''
                        ')'
                    ').json()[\'state\'] == \'success\')'
                '"; '
                'do i=$((i+1)); '
                    'if [ $i -gt ${GITHUB_API_POLL_RETRIES} ]; '
                    'then exit 1; '
                    'fi; '
                    'sleep ${GITHUB_API_POLL_WAIT_S}; '
                'done'
            ]
        )
    )
    # pylint: enable=bad-continuation

    download_stage = pipeline.ensure_stage(DOWNLOAD_STAGE_NAME).set_clean_working_dir()
    swagger_codegen_job = download_stage.ensure_job(
        SWAGGER_CODEGEN_JOB_NAME
    ).ensure_artifacts(
        {BuildArtifact(SWAGGER_JAR)}
    )
    swagger_codegen_job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                'wget ${{SWAGGER_CODEGEN_JAR}} -O {swagger_jar}'.format(swagger_jar=SWAGGER_JAR)
            ]
        )
    )

    build_stage = pipeline.ensure_stage(BUILD_STAGE_NAME).set_clean_working_dir()
    swagger_flatten_job = build_stage.ensure_job(SWAGGER_FLATTEN_JOB_NAME).ensure_artifacts(
        {
            BuildArtifact('api-manager/swagger-build-artifacts/swagger.json')
        }
    )

    artifact_params = {
        'pipeline': pipeline.name,
        'stage': DOWNLOAD_STAGE_NAME,
        'job': SWAGGER_CODEGEN_JOB_NAME,
        'src': FetchArtifactFile(SWAGGER_JAR),
        'dest': API_MANAGER_WORKING_DIR
    }
    swagger_flatten_job.add_task(FetchArtifactTask(**artifact_params))
    swagger_flatten_job.add_task(ExecTask(['make', 'build'], working_dir=API_MANAGER_WORKING_DIR))

    package_source_job = build_stage.ensure_job(
        PACKAGE_SOURCE_JOB_NAME
    ).ensure_artifacts(
        {BuildArtifact('api-manager')}
    )
    package_source_job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c', 'pip install -t python-libs -r requirements/base.txt'
            ],
            working_dir=API_MANAGER_WORKING_DIR
        )
    )


if __name__ == '__main__':
    pipeline_script(install_pipelines)
