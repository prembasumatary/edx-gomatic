#!/usr/bin/env python
"""
Script to install pipeline that can build ora2 sandboxes.
"""

import sys
from os import path

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

# pylint: disable=wrong-import-position
from edxpipelines.patterns import tasks
from edxpipelines.materials import TUBULAR
from edxpipelines import constants
from edxpipelines.pipelines.script import pipeline_script


def install_pipelines(configurator, config, env_configs):  # pylint: disable=unused-argument
    """
    Variables needed for this pipeline:
    - gocd_username
    - gocd_password
    - gocd_url
    - configuration_secure_rep
    - jenkins_user_token
    - jenkins_job_token
    """

    pipeline = configurator.ensure_pipeline_group(constants.ORA2_PIPELINE_GROUP_NAME) \
                           .ensure_replacement_of_pipeline(constants.BUILD_ORA2_SANDBOX_PIPELINE_NAME)

    pipeline.ensure_material(TUBULAR())

    pipeline.ensure_environment_variables(
        {
            'DNS_NAME': '',
            'NAME_TAG': '',
            'EDXAPP_VERSION': 'master',
            'ORA2_VERSION': 'master',
            'CONFIGURATION_VERSION': 'master',
            'CONFIGURATION_SOURCE_REPO': 'https://github.com/edx/configuration.git',
            'CONFIGURATION_SECURE_VERSION': 'master',
            'CONFIGURATION_INTERNAL_VERSION': 'master',
            'NOTIFY_ON_FAILURE': 'tnl-dev@edx.org'
        }
    )

    pipeline.ensure_unencrypted_secure_environment_variables(
        {
            'JENKINS_USER_TOKEN': config['jenkins_user_token'],
            'JENKINS_JOB_TOKEN': config['jenkins_job_token']
        }
    )

    # Create the Create Sandbox stage, job, and task
    jenkins_create_ora2_sandbox_stage = pipeline.ensure_stage(
        constants.CREATE_ORA2_SANDBOX_STAGE_NAME
    )
    jenkins_create_ora2_sandbox_job = jenkins_create_ora2_sandbox_stage.ensure_job(
        constants.CREATE_ORA2_SANDBOX_JOB_NAME
    )
    tasks.generate_package_install(jenkins_create_ora2_sandbox_job, 'tubular')

    # Keys need to be lower case for this job to use them
    create_ora2_sandbox_jenkins_params = {
        'dns_name': '$DNS_NAME',
        'name_tag': '$NAME_TAG',
        'edxapp_version': '$EDXAPP_VERSION',
        'configuration_version': '$CONFIGURATION_VERSION',
        'configuration_source_repo': '$CONFIGURATION_SOURCE_REPO',
        'configuration_secure_version': '$CONFIGURATION_SECURE_VERSION',
        'configuration_internal_version': '$CONFIGURATION_INTERNAL_VERSION',
        'basic_auth': 'false'
    }
    tasks.trigger_jenkins_build(
        jenkins_create_ora2_sandbox_job,
        constants.ORA2_JENKINS_URL,
        constants.ORA2_JENKINS_USER_NAME,
        constants.CREATE_ORA2_SANDBOX_JENKINS_JOB_NAME,
        create_ora2_sandbox_jenkins_params,
        timeout=75 * 60
    )

    # Create the Set Ora2 Version stage, job, and task
    jenkins_set_ora2_version_stage = pipeline.ensure_stage(
        constants.SET_ORA2_VERSION_STAGE_NAME
    )
    jenkins_set_ora2_version_job = jenkins_set_ora2_version_stage.ensure_job(
        constants.SET_ORA2_VERSION_JOB_NAME
    )
    tasks.generate_package_install(jenkins_set_ora2_version_job, 'tubular')
    # Keys need to be upper case for this job to use them
    set_ora2_version_jenkins_params = {
        'SANDBOX_HOST': '${DNS_NAME}.sandbox.edx.org',  # uses a different variable name for set version
        'ORA2_VERSION': '$ORA2_VERSION',
        'NOTIFY_ON_FAILURE': '$NOTIFY_ON_FAILURE'
    }
    tasks.trigger_jenkins_build(
        jenkins_set_ora2_version_job,
        constants.ORA2_JENKINS_URL,
        constants.ORA2_JENKINS_USER_NAME,
        constants.SET_ORA2_VERSION_JENKINS_JOB_NAME,
        set_ora2_version_jenkins_params
    )

if __name__ == "__main__":
    pipeline_script(install_pipelines)
