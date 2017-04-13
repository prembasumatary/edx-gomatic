#!/usr/bin/env python
"""
Script to install pipelines run CI for vagrant devstack
"""
import sys
from os import path

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

# pylint: disable=wrong-import-position
from edxpipelines.pipelines.script import pipeline_script
from edxpipelines.patterns.tasks import common


def install_pipelines(configurator, config):
    pipeline = configurator.ensure_pipeline_group("CI") \
        .ensure_replacement_of_pipeline("Vagrant_Devstack_CI")

    build_stage = pipeline.ensure_stage("build_vagrant_devstack")
    # TODO: Build the stage

    build_job = build_stage.ensure_job("build_vagrant_devstack_job")
    # TODO: Build the job and tasks
    build_job.ensure_task(
        common.bash_task("vagrant provision", working_dir="")
    )

    # TODO: run the smoke tests
    test_stage = pipeline.ensure_stage("test_e2e_vagrant_devstack")
    test_job = test_stage.ensure_job("test_e2e_vagrant_devstack_job")
    test_job.ensure_task(
        common.bash_task("blah", working_dir="")
    )


if __name__ == '__main__':
    pipeline_script(install_pipelines)
