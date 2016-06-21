import yaml
from copy import copy


class MergeConflict(Exception):
    pass


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
        return []
    elif len(args) == 1:
        return args[0]
    else:
        return reduce(_deep_dict_merge, args)


def _deep_dict_merge(a, b):
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
                raise MergeConflict('Conflict at key: {} . A value: {} -- B value: {}'.format(key, ret_dict[key], b[key]))
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
    line of a pipline script

    Args:
        file_paths (list<str>): a list of strings to the input yaml files
        dicts (list<dict>): A list of dictionaries

    Returns:
        dict: all the parameters merged

    Raises:
        TypeError: if a and b are not both dicts
        MergeConflict: if a key exists with different values between the two dictionaries
    """
    file_variables = [load_yaml_from_file(f) for f in file_paths]
    dict_vars = []
    for d in dicts:
        if isinstance(d, list):
            # try to convert to a dict as it could be a list of tuples from click
            dict_vars.append({k: v for k, v in d})
        elif isinstance(d, dict):
            dict_vars.append(d)
        else:
            raise ValueError("dicts contains an instance that is not a dictionary {}".format(d.__class__))

    [file_variables.append(d) for d in dict_vars]
    return dict_merge(*file_variables)