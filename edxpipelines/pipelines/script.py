import click


def compose_decorators(func, *decs):
    """
    Compose a set of decorators (as if they were written in
    the same order on the function declaration).
    """
    for dec in reversed(decs):
        func = dec(func)
    return func


def pipeline_script(func):
    """
    Make a function a pipeline system creation script.
    """
    return compose_decorators(
        func,
        click.command(),
        click.option(
            '--save-config', 'save_config_locally',
            envvar='SAVE_CONFIG',
            help='Save the pipeline configuration xml locally.',
            required=False,
            default=False,
            is_flag=True
        ),
        click.option(
            '--dry-run',
            envvar='DRY_RUN',
            help='Perform a dry run of the pipeline installation, and save the pre/post xml configurations locally.',
            required=False,
            default=False,
            is_flag=True
        ),
        click.option(
            '--variable_file', 'variable_files',
            multiple=True,
            help='Path to yaml variable file with a dictionary of key/value pairs to be used as variables in the script.',
            required=False,
            default=[]
        ),
        click.option(
            '--env-variable-file', 'env_variable_files',
            multiple=True,
            type=(unicode, click.Path(dir_okay=False, exists=True)),
            help='An environment, and a variable file that applies only to that environment',
            required=False,
            default=[],
        ),
        click.option(
            '-e', '--variable', 'cmd_line_vars',
            multiple=True,
            help='Key/value used as a replacement variable in this script, as in KEY=VALUE.',
            required=False,
            type=(str, str),
            nargs=2,
            default={}
        ),
    )