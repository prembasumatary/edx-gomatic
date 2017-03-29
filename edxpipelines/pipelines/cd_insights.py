#!/usr/bin/env python
"""
Script to install pipelines that can deploy edX insights.
"""
from functools import partial
import sys
from os import path

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

# pylint: disable=wrong-import-position
from gomatic import GitMaterial

from edxpipelines.patterns.pipelines import generate_service_deployment_pipelines
from edxpipelines.pipelines.script import pipeline_script
from edxpipelines.utils import EDP


def install_pipelines(configurator, config):
    """
    Generates pipelines used to deploy the insights service to stage, loadtest,
    prod-edx, and prod-edge.
    """
    edp = EDP(None, None, 'insights')

    partial_app_material = partial(
        GitMaterial,
        'https://github.com/edx/edx-analytics-dashboard.git',
        # Material name is required to label pipelines with a commit SHA. GitMaterials
        # return their SHA when referenced by name.
        material_name=edp.play,
        polling=True,
        destination_directory=edp.play,
    )

    generate_service_deployment_pipelines(configurator, config, edp, partial_app_material,
                                          prod_deployments=['edx', 'edge'])


if __name__ == '__main__':
    pipeline_script(install_pipelines, environments=('stage-edx', 'loadtest-edx', 'prod-edx', 'prod-edge'))
