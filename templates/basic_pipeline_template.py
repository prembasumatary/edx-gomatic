#!/usr/bin/env python

"""
This script provides a basic template for pipelines reversed engineered by gomatic.

Simply reverse engineer a script:
python -m gomatic.go_cd_configurator --ssl -s gocd.tools.edx.org -p <pipeline_name> --username <username> --password <password>

Then copy/paste the scripty parts in to the install_pipeline method.

Hoping to write a script to make this more automated soon.
"""
import sys
from os import path
sys.path.append( path.dirname( path.dirname( path.abspath(__file__) ) ) )

import click
from edxpipelines.utils import merge_files_and_dicts
from gomatic import *


@click.command()
@click.option('--save-config', 'save_config_locally', envvar='SAVE_CONFIG', help='Save the pipeline configuration xml locally', required=False, default=False)
@click.option('--dry-run', envvar='DRY_RUN', help='do a dry run of  the pipeline installation, and save the pre/post xml configurations locally', required=False, default=True)
@click.option('--variable_file', 'variable_files', multiple=True, help='path to yaml variable file with a dictionary of key/value pairs to be used as variables in the script', required=False)
@click.option('-e', '--variable', 'cmd_line_vars', multiple=True, help='key/value of a variable used as a replacement in this script', required=False, type=(str, str), nargs=2)
def install_pipeline(save_config_locally=False, dry_run=False, variable_files=[], cmd_line_vars={}):
    """
    TODO: PUT YOUR PIPELINE BUILDING SCRIPT HERE!
    """
    config = merge_files_and_dicts(variable_files, cmd_line_vars)
    print config


if __name__ == "__main__":
    install_pipeline()