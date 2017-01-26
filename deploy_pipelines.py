#!/usr/bin/env python
import logging
import pprint
import subprocess
import sys

import click
import yaml
from edxpipelines.deploy import ensure_pipeline

logging.basicConfig(stream=sys.stdout, level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S')


def parse_config(environment, config_file_path, script_filter=None):
    """
    Parses the configuration file for a given environment. returns only scripts that are enabled.

    If script_filter is passed in, only the script name that matches the script_filter will be returned

    Args:
        environment (str): The environment of the scripts
        config_file_path (str): Location of the configuration file
        script_filter (str): Filter for a specific script, if None all enabled scripts are returned.

    Returns:
        list of dict
    """
    with open(config_file_path, 'r') as file:
        config = yaml.safe_load(file)
    result = []
    for script in config[environment]:
        if script.pop('enabled'):
            if script_filter is None or script_filter == script['script']:
                result.append(script)
    return result


def print_success_report(success):
    print "Succesfully run scripts:"
    for item in success:
        logging.info(pprint.pformat(item))


def print_failure_report(failures):
    print "Scripts failed:"
    for failure in failures:
        logging.info("script:\n{}".format(pprint.pformat(failure)))


@click.command()
@click.argument('environment', required=True)
@click.option('--config_file', '-f', help='Path to the configuration file', required=True)
@click.option('--verbose', '-v', is_flag=True)
@click.option('--script', help='optional, specify the script to run.', default=None)
@click.option('--dry-run',
        help='run all pipelines in dry-run mode.',
        default=False,
        is_flag=True,
)
def run_pipelines(environment, config_file, script, verbose, dry_run):
    """

    Args:
        environment (str): The environment in the config file to run
        config_file (str): Path to the configuration file
        script (str): The script to run.
        verbose (bool): if true set the logging level to debug

    Returns:

    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    scripts = parse_config(environment, config_file, script)

    if not scripts:
        print "No scripts to run!"
        exit(1)

    success = []
    failures = []
    for script in scripts:
        script_name = script.pop('script')
        try:
            ensure_pipeline(
                script_name,
                dry_run=dry_run,
                **script
            )
            success.append(script_name)
        except subprocess.CalledProcessError as exc:
            failures.append({
                'command': subprocess.list2cmdline(exc.cmd),
                'script': script_name,
                'args': script,
                'error': exc.output.split("\n")
            })

    if len(success) > 0:
        print_success_report(success)

    if len(failures) > 0:
        print_failure_report(failures)
        exit(1)

    exit(0)



if __name__ == '__main__':
    run_pipelines()
