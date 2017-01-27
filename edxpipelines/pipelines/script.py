import functools
from itertools import groupby

import click
from gomatic import *

import edxpipelines.utils as utils


def compose_decorators(func, *decs):
    """
    Compose a set of decorators (as if they were written in
    the same order on the function declaration).
    """
    for dec in reversed(decs):
        func = dec(func)
    return func


def pipeline_script(environments=()):
    """
    Make a function a pipeline system creation script.
    """
    def decorator(func):
        @click.command()
        @click.option(
            '--save-config', 'save_config_locally',
            envvar='SAVE_CONFIG',
            help='Save the pipeline configuration xml locally.',
            required=False,
            default=False,
            is_flag=True
        )
        @click.option(
            '--dry-run',
            envvar='DRY_RUN',
            help='Perform a dry run of the pipeline installation, and save the pre/post xml configurations locally.',
            required=False,
            default=False,
            is_flag=True
        )
        @click.option(
            '--variable_file', 'variable_files',
            multiple=True,
            help='Path to yaml variable file with a dictionary of key/value pairs to be used as variables in the script.',
            required=False,
            default=[]
        )
        @click.option(
            '--env-variable-file', 'env_variable_files',
            multiple=True,
            type=(click.Choice(environments), click.Path(dir_okay=False, exists=True)),
            help='An environment, and a variable file that applies only to that environment',
            required=False,
            default=[],
        )
        @click.option(
            '-e', '--variable', 'cmd_line_vars',
            multiple=True,
            help='Key/value used as a replacement variable in this script, as in KEY=VALUE.',
            required=False,
            type=(str, str),
            nargs=2,
            default={}
        )
        @functools.wraps(func)
        def cli(save_config_locally, dry_run, variable_files, env_variable_files, cmd_line_vars):
            # Merge the configuration files/variables together
            config = utils.merge_files_and_dicts(variable_files, list(cmd_line_vars,))
            env_vars = {
                env: tuple(file for _, file in files)
                for env, files
                in groupby(
                    sorted(env_variable_files),
                    lambda (env, file): env,
                )
            }
            env_configs = {
                env: utils.merge_files_and_dicts(variable_files + files, list(cmd_line_vars))
                for env, files in env_vars.items()
            }

            # Create the pipeline
            configurator = GoCdConfigurator(HostRestClient(
                config['gocd_url'],
                config['gocd_username'],
                config['gocd_password'],
                ssl=True
            ))
            return_val = func(configurator, config, env_configs)
            configurator.save_updated_config(save_config_locally=save_config_locally, dry_run=dry_run)
            return return_val

        return cli
    return decorator
