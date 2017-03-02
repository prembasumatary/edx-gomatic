#!/usr/bin/env python
"""
Script for installing pipelines used to deploy the ecommerce service.
"""
import sys
from os import path

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

# pylint: disable=wrong-import-position
from gomatic import GitMaterial

from edxpipelines.patterns.pipelines import generate_service_deployment_pipeline
from edxpipelines.pipelines.script import pipeline_script
from edxpipelines.utils import EDP


def install_pipelines(configurator, config, env_configs):
    """
    Generates a pipeline used to deploy the ecommerce service to stage, loadtest, and prod.
    """
    edp = EDP(None, 'edx', 'ecommerce')

    app_material = GitMaterial(
        'https://github.com/edx/ecommerce.git',
        material_name=edp.play,
        branch='renzo/pipeline-test',
        polling=True,
        destination_directory=edp.play
    )

    generate_service_deployment_pipeline(configurator, config, env_configs, edp, app_material)


if __name__ == '__main__':
    pipeline_script(install_pipelines, environments=('stage', 'loadtest', 'prod'))
