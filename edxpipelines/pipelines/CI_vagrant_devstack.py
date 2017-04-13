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

    for material in [E2E_TESTS, CONFIGURATION]:
        pipeline.ensure_material(
            GitMaterial(
                url=material['url'],
                branch=material['branch'],
                material_name=material['material_name'],
                polling=material['polling'],
                destination_directory=material['destination_directory'],
                ignore_patterns=set(material['ignore_patterns'])
            )
        )

    provision_devstack(pipeline)

    run_e2e(pipeline)


def provision_devstack(pipeline):
    build_stage = pipeline.ensure_stage("build_vagrant_devstack")
    build_job = build_stage.ensure_job("build_vagrant_devstack_job")
    # TODO: Build the job and tasks
    build_job.ensure_task(
        common.bash_task("vagrant provision", working_dir=constants.PUBLIC_CONFIGURATION_DIR) # NOT SURE ON DIR?
    )


def run_e2e(pipeline):
    # TODO: run the smoke tests
    test_stage = pipeline.ensure_stage("test_e2e_vagrant_devstack")
    test_job = test_stage.ensure_job("test_e2e_vagrant_devstack_job")

    # TODO Import the course
    test_job.ensure_task(
        common.bash_task("vagrant scp ...", working_dir="")
    )

    #TODO run the tests
    test_job.ensure_task(
        common.bash_task("e2e something something", working_dir="")
    )


if __name__ == '__main__':
    pipeline_script(install_pipelines)
