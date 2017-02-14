"""
Utility functions needed by edX gomatic code.
"""
from collections import namedtuple
from copy import copy

import yaml

from gomatic import FetchArtifactFile, FetchArtifactDir, FetchArtifactTask


class MergeConflict(Exception):
    """Raised when a merge conflict is found when trying to deep-merge dictionaries."""
    pass


class ArtifactLocation(namedtuple(
        "ArtifactLocationBase",
        [
            'pipeline', 'stage', 'job', 'file_name', 'is_dir'
        ]
)):
    """
    The identifying information for an artifact.
    """
    __slots__ = ()

    def as_fetch_task(self, dest):
        """
        Return a :class:`~gomatic.FetchArtifactTask` that will retrieve
        this artifact.
        """
        if self.is_dir:
            src = FetchArtifactDir(self.file_name)
        else:
            src = FetchArtifactFile(self.file_name)  # pylint: disable=redefined-variable-type

        return FetchArtifactTask(
            pipeline=self.pipeline,
            stage=self.stage,
            job=self.job,
            src=src,
            dest=dest
        )

# This sets the is_dir argument for ArtifactLocation to False by default
ArtifactLocation.__new__.__defaults__ = (False,)


def dict_merge(*args):
    """
    Wraps the _dict_merge function. Pass this method a bunch of dictionaries and they will be merged.

    dict_merge(dict1, dict2, dict3, dict4)

    Args:
        *args: a list of dictionaries

    Returns:
        dict: a merged dict

    """
    if len(args) < 1:
        return {}
    elif len(args) == 1:
        return args[0]
    else:
        return reduce(_deep_dict_merge, args)


def _deep_dict_merge(a, b):  # pylint: disable=invalid-name
    """
    Deep merges 2 dictionaries together.

    Args:
        a (dict): first dictionary
        b (dict): second dictionary

    Returns:
        dict: a and b merged in to a single dict

    Raises:
        TypeError: if a and b are not both dicts
        MergeConflict: if a key exists with different values between the two dictionaries
    """
    if not isinstance(a, dict) or not isinstance(b, dict):
        raise TypeError("Both arguments must be a dict. Can not merge {} and {}".format(a.__class__, b.__class__))

    ret_dict = copy(a)

    for key in b:
        if key in ret_dict:
            if isinstance(ret_dict[key], dict) and isinstance(b[key], dict):
                ret_dict[key] = _deep_dict_merge(ret_dict[key], b[key])
            elif ret_dict[key] == b[key]:
                pass  # same leaf value
            else:
                raise MergeConflict(
                    'Conflict at key: {} . A value: {} -- B value: {}'.format(
                        key, ret_dict[key], b[key]
                    )
                )
        else:
            ret_dict[key] = b[key]
    return ret_dict


def load_yaml_from_file(filename):
    """
    Loads a yaml file from disk

    Args:
        filename: path to the yaml file to open

    Returns:
        dict: representing the yaml in the file
    """
    with open(filename, 'r') as stream:
        return yaml.safe_load(stream)


def merge_files_and_dicts(file_paths, dicts):
    """
    Merges together yaml files with key/value pairs with dictonaries. Useful for parsing the inputs from the command
    line of a pipeline script

    Args:
        file_paths (list<str>): a list of strings to the input yaml files
        dicts (list<dict>): A list of dictionaries (can also be a list of (k,v) tuples)

    Returns:
        dict: all the parameters merged

    Raises:
        TypeError: if a and b are not both dicts
        MergeConflict: if a key exists with different values between the two dictionaries
    """
    file_variables = [load_yaml_from_file(f) for f in file_paths]
    dict_vars = []
    for dict_ in dicts:
        if isinstance(dict_, list):
            # try to convert to a dict as it could be a list of tuples from click
            dict_vars.append({k: v for k, v in dict_})
        elif isinstance(dict_, dict):
            dict_vars.append(dict_)
        else:
            raise ValueError("dicts contains an instance that is not a dictionary {}".format(dict_.__class__))

    file_variables.extend(dict_vars)
    return dict_merge(*file_variables)
