#!/usr/bin/env python
import sys
from os import path
import click
from gomatic import *

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

from edxpipelines import utils
from edxpipelines import constants
from edxpipelines.patterns import stages
from edxpipelines.patterns import tasks
from edxpipelines.pipelines.script import pipeline_script


def install_pipelines(configurator, config, env_configs):
    """
    Variables needed for this pipeline:
    materials: A list of dictionaries of the materials used in this pipeline
    upstream_pipelines: a list of dictionaries of the upstream pipelines that feed in to the manual verification
    """
    pipeline = configurator.ensure_pipeline_group(config['pipeline_group'])\
                           .ensure_replacement_of_pipeline(config['pipeline_name'])

    for material in config['materials']:
        pipeline.ensure_material(
            GitMaterial(
                url=material['url'],
                branch=material['branch'],
                material_name=material['material_name'],
                polling=material['polling'],
                destination_directory=material['destination_directory'],
                ignore_patterns=material['ignore_patterns']
            )
        )

    for material in config['upstream_pipelines']:
        pipeline.ensure_material(
            PipelineMaterial(
                pipeline_name=material['pipeline_name'],
                stage_name=material['stage_name'],
                material_name=material['material_name']
            )
        )

    # What this accomplishes:
    # When a pipeline such as edx stage runs this pipeline is downstream. Since the first stage is automatic
    # the git materials will be carried over from the first pipeline.
    #
    # The second stage in this pipeline requires manual approval.
    #
    # This allows the overall workflow to remain paused while manual verification is completed and allows the git
    # materials to stay pinned.
    #
    # Once the second phase is approved, the workflow will continue and pipelines downstream will continue to execute
    # with the same pinned materials from the upstream pipeline.
    stages.generate_armed_stage(pipeline, constants.INITIAL_VERIFICATION_STAGE_NAME)

    # For now, you can only trigger builds on a single jenkins server, because you can only
    # define a single username/token.
    # And all the jobs that you want to trigger need the same job token defined.
    # TODO: refactor when required so that each job can define their own user and job tokens
    pipeline.ensure_unencrypted_secure_environment_variables(
        {
            'JENKINS_USER_TOKEN': config['jenkins_user_token'],
            'JENKINS_JOB_TOKEN': config['jenkins_job_token']
        }
    )

    # Create the stage with the Jenkins jobs
    jenkins_stage = pipeline.ensure_stage(constants.JENKINS_VERIFICATION_STAGE_NAME)
    jenkins_stage.set_has_manual_approval()
    jenkins_user_name = config['jenkins_user_name']

    for jenkins in config['jenkins_verifications']:
        pipeline_job_name = jenkins['pipeline_job_name']
        jenkins_url = jenkins['url']
        jenkins_job_name = jenkins['job_name']
        key, _, param = jenkins['param'].partition(' ')
        jenkins_param = {key: param}

        job = jenkins_stage.ensure_job(pipeline_job_name)
        tasks.generate_package_install(job, 'tubular')
        tasks.trigger_jenkins_build(job, jenkins_url, jenkins_user_name, jenkins_job_name, jenkins_param)

    manual_verification_stage = pipeline.ensure_stage(constants.MANUAL_VERIFICATION_STAGE_NAME)
    manual_verification_stage.set_has_manual_approval()
    manual_verification_job = manual_verification_stage.ensure_job(constants.MANUAL_VERIFICATION_JOB_NAME)
    manual_verification_job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                'echo Manual Verification run number $GO_PIPELINE_COUNTER completed by $GO_TRIGGER_USER'
            ],
        )
    )


if __name__ == "__main__":
    pipeline_script(install_pipelines)
