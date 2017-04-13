#!/usr/bin/env python
"""
Script to install pipelines run CI for vagrant devstack
"""
import sys
from os import path

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

# pylint: disable=wrong-import-position
from edxpipelines import constants
from edxpipelines.pipelines.script import pipeline_script
from edxpipelines.patterns.tasks import common
from edxpipelines.materials import E2E_TESTS, CONFIGURATION

from gomatic import GitMaterial


def install_pipelines(configurator, config):
    pipeline = configurator.ensure_pipeline_group("CI") \
        .ensure_replacement_of_pipeline("Vagrant_Devstack_CI")

    for material in (E2E_TESTS, CONFIGURATION):
        pipeline.ensure_material(material())

    # Make sure port is open for the e2e tests
    provision_devstack(pipeline)
    # run_e2e(pipeline)


# add resource to job level
def provision_devstack(pipeline):
    build_stage = pipeline.ensure_stage("build_vagrant_devstack")
    build_job = build_stage.ensure_job("build_vagrant_devstack_job")

    # Install vbguest
    build_job.ensure_task(
        common.bash_task('vagrant plugin install vagrant-vbguest', working_dir=constants.PUBLIC_CONFIGURATION_DEVSTACK_DIR)
    )

    # Stop any running Vagrant image
    build_job.ensure_task(
        common.bash_task('vagrant halt', working_dir=constants.PUBLIC_CONFIGURATION_DEVSTACK_DIR)
    )

    # # Destroy any Vagrant image
    # build_job.ensure_task(
    #     common.bash_task('vagrant destroy', working_dir=constants.PUBLIC_CONFIGURATION_DEVSTACK_DIR)
    # )
    #
    # # Remove .vagrant directory
    # build_job.ensure_task(
    #     common.bash_task('rm -rf .vagrant', working_dir=constants.PUBLIC_CONFIGURATION_DEVSTACK_DIR)
    # )

    # Bring up the image
    build_job.ensure_task(
        common.bash_task("vagrant up --provider virtualbox", working_dir=constants.PUBLIC_CONFIGURATION_DEVSTACK_DIR)
    )


def run_e2e(pipeline):
    # TODO: run the smoke tests
    test_stage = pipeline.ensure_stage('test_e2e_vagrant_devstack')
    test_job = test_stage.ensure_job('test_e2e_vagrant_devstack_job')
    test_job.ensure_resource('vagrant_devstack')
    test_job.ensure_environment_variables(
        {
            'BASIC_AUTH_USER': '',
            'BASIC_AUTH_PASSWORD': '',
            'USER_LOGIN_EMAIL': 'staff@example.com',
            'USER_LOGIN_PASSWORD': 'edx',
            'STUDIO_BASE_URL': 'http://localhost:8001/',
            'LMS_BASE_URL': 'http://localhost:8000/',
        }
    )
    # install configuration requiremenst
    common.generate_requirements_install(
        test_job,
        working_dir='{}/requirements'.format('edx-e2e-tests')
    )

    # Install page objects
    test_job.ensure_task(
        common.bash_task('paver install_pages', working_dir='edx-e2e-tests')
    )

    # TODO Import the course
    test_job.ensure_task(
        common.bash_task('vagrant scp ...', working_dir='')
    )

    # TODO run the tests
    test_job.ensure_task(
        common.bash_task('paver e2e_test', working_dir='')
    )


if __name__ == '__main__':
    pipeline_script(install_pipelines)
