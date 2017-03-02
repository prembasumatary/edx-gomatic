#!/usr/bin/env python
"""
Script to install pipelines that can deploy an AMI.
"""
import sys
from os import path

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

# pylint: disable=wrong-import-position
from edxpipelines.patterns import pipelines
from edxpipelines.pipelines.script import pipeline_script


def install_pipelines(configurator, config, env_configs):  # pylint: disable=unused-argument
    """
    Variables needed for this pipeline:
    - gocd_username
    - gocd_password
    - gocd_url
    - pipeline_name
    - pipeline_group
    - asgard_api_endpoints
    - asgard_token
    - aws_access_key_id
    - aws_secret_access_key

    To run this script:
    python edxpipelines/pipelines/deploy_ami.py \
        --variable_file ../gocd-pipelines/gocd/vars/tools/deploy_edge_ami.yml \
        --variable_file ../gocd-pipelines/gocd/vars/tools/tools.yml
    python edxpipelines/pipelines/deploy_ami.py \
        --variable_file ../gocd-pipelines/gocd/vars/tools/deploy_edx_ami.yml \
        --variable_file ../gocd-pipelines/gocd/vars/tools/tools.yml
    python edxpipelines/pipelines/deploy_ami.py \
        --variable_file ../gocd-pipelines/gocd/vars/tools/deploy-mckinsey-ami.yml \
        --variable_file ../gocd-pipelines/gocd/vars/tools/tools.yml
    """
    pipeline_params = {
        "pipeline_name": config['pipeline_name'],
        "pipeline_group": config['pipeline_group'],
        "asgard_api_endpoints": config['asgard_api_endpoints'],
        "asgard_token": config['asgard_token'],
        "aws_access_key_id": config['aws_access_key_id'],
        "aws_secret_access_key": config['aws_secret_access_key']
    }
    configurator = pipelines.generate_ami_deployment_pipeline(configurator, **pipeline_params)
    print "done"

if __name__ == "__main__":
    pipeline_script(install_pipelines)
