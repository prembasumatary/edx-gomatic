#!/usr/bin/env python
"""
Script to install pipelines to clean up old ASGs.
"""
import sys
from os import path

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

# pylint: disable=wrong-import-position
from edxpipelines import materials
from edxpipelines.patterns import stages
from edxpipelines.pipelines.script import pipeline_script


def install_pipelines(configurator, config):
    """
    Variables needed for this pipeline:
    - aws_access_key_id
    - aws_secret_access_key
    - edx_deployment
    """
    for env_config in config.by_environments():
        pipeline_name = 'Instance-Cleanup-{}'.format(env_config['edx_deployment'])
        pipeline = configurator.ensure_pipeline_group('Janitors')\
                               .ensure_replacement_of_pipeline(pipeline_name)\
                               .set_timer('0 0,30 * * * ?')\
                               .set_git_material(materials.TUBULAR())

        stages.generate_cleanup_dangling_instances(
            pipeline,
            env_config['aws_access_key_id'],
            env_config['aws_secret_access_key'],
            name_match_pattern='gocd automation run*',
            max_run_hours=24,
            skip_if_tag='do_not_delete'
        )

if __name__ == "__main__":
    pipeline_script(install_pipelines, environments=('edx', 'edge', 'mckinsey'))
