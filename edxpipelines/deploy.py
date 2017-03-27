"""
Tools for deploying gomatic-built pipelines.
"""

import logging
import subprocess
import tempfile

from .canonicalize import canonicalize_file
from .topology import simplify_file


def ensure_pipeline(script, dry_run=False, save_config_locally=False, topology=False, **kwargs):
    """
    Execute a pipeline install script, optionally saving the config for later inspection.

    Arguments:
        script: The pipeline script to execute.
        dry_run: If True, don't actually modify the GoCD server.
        save_config_locally: If True, store the config before and after the script executes
            as config-before.xml and config-after.xml.
        kwargs: Any additional parameters to be passed to the script. These parameters
            will be sorted, and any values that are lists will have each value in the
            list passed as a separate copy of the option flag. For instance, the kwargs

                {"foo": 1, "bar": [2, 3]}

            would result in the options

                --foo 1 --bar 2 --bar 3
    """
    script_args = []

    if dry_run:
        script_args.append('--dry-run')

    if save_config_locally:
        script_args.append('--save-config')

    for key, args in sorted(kwargs.items()):
        if not isinstance(args, list):
            args = [args]
        for arg in args:
            script_args.append('--{}'.format(key))
            if not isinstance(arg, list):
                arg = [arg]
            script_args.extend(arg)

    command = ['python', script] + script_args
    logging.debug("Executing script: {}".format(subprocess.list2cmdline(command)))
    result = subprocess.check_output(command, stderr=subprocess.STDOUT)
    if dry_run and save_config_locally:
        with tempfile.NamedTemporaryFile() as before_out, tempfile.NamedTemporaryFile() as after_out:
            diff_func = simplify_file if topology else canonicalize_file
            diff_func('config-before.xml', before_out)
            diff_func('config-after.xml', after_out)
            subprocess.call([
                'git', '--no-pager',
                'diff', '--no-index', '--color-words',
                before_out.name, after_out.name
            ])

    return result
