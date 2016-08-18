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
        .set_label_template("${api-manager}")\
        .set_git_material(GitMaterial(config['github']['server_uri'] + '/' + config['github']['repository'], branch="#{GIT_BRANCH}", material_name="api-manager", destination_directory="api-manager"))\
        .ensure_parameters({'GIT_BRANCH': config['github']['branch']})

    pipeline.ensure_environment_variables({
        'SWAGGER_CODEGEN_JAR': config['swagger_codegen_jar'],
        'GITHUB_API_REPO': config['github']['repository'],
        'GITHUB_API_URI': config['github']['api_uri'],
        'GITHUB_API_POLL_WAIT_S': config['github']['api_poll_wait_s'],
        'GITHUB_API_POLL_RETRIES': config['github']['api_poll_retries']
    })

    # Note, need to move this Github poll hack to something less of a hack at some point.
    stage = pipeline.ensure_stage("setup")
    job = stage.ensure_job("wait-for-travis")
    job.add_task(ExecTask(['/bin/bash', '-c', 'i=0; until python -c "import requests; assert(requests.get(\'${GITHUB_API_URI}/${GITHUB_API_REPO}/commits/{}/status\'.format(\'${GO_REVISION_API_MANAGER}\')).json()[\'state\'] == \'success\')"; do i=$((i+1)); if [ $i -gt ${GITHUB_API_POLL_RETRIES} ]; then exit 1; fi; sleep ${GITHUB_API_POLL_WAIT_S}; done']))

    stage = pipeline.ensure_stage("download").set_clean_working_dir()
    job = stage.ensure_job("swagger-codegen").ensure_artifacts({BuildArtifact("swagger-codegen-cli.jar")})
    job.add_task(ExecTask(['/bin/bash', '-c', 'wget ${SWAGGER_CODEGEN_JAR} -O swagger-codegen-cli.jar']))

    stage = pipeline.ensure_stage("build").set_clean_working_dir()
    job = stage.ensure_job("swagger-flatten").ensure_artifacts({BuildArtifact("api-manager/swagger-build-artifacts/swagger.json")})
    job.add_task(FetchArtifactTask("", "download", "swagger-codegen", FetchArtifactFile("swagger-codegen-cli.jar"), dest="api-manager"))
    job.add_task(ExecTask(['make', 'build'], working_dir="api-manager"))
    job = stage.ensure_job("package-source").ensure_artifacts({BuildArtifact("api-manager")})
    job.add_task(ExecTask(['/bin/bash', '-c', '/usr/bin/pip install -t python-libs -r requirements/base.txt'], working_dir="api-manager"))

    configurator.save_updated_config(save_config_locally=save_config_locally, dry_run=dry_run)

if __name__ == "__main__":
    install_pipeline()
