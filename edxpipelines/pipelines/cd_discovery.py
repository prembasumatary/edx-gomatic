#!/usr/bin/env python
"""
Script for installing pipelines used to deploy the discovery service.
"""
from functools import partial
from os import path
import sys

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

# pylint: disable=wrong-import-position
from gomatic import GitMaterial

from edxpipelines.patterns.pipelines import generate_service_deployment_pipelines
from edxpipelines.pipelines.script import pipeline_script
from edxpipelines.utils import EDP


def install_pipelines(configurator, config):
    """
    Generates pipelines used to deploy the discovery service to stage, loadtest, and prod.
    """
    edp = EDP(None, 'edx', 'discovery')

    partial_app_material = partial(
        GitMaterial,
        'https://github.com/edx/course-discovery.git',
        # Material name is required to label pipelines with a commit SHA. GitMaterials
        # return their SHA when referenced by name.
        material_name=edp.play,
        polling=True,
        destination_directory=edp.play
    )

    generate_service_deployment_pipelines(configurator, config, edp, partial_app_material)


if __name__ == '__main__':
    pipeline_script(install_pipelines, environments=('stage', 'loadtest', 'prod'))
