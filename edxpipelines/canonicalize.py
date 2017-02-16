#!/usr/bin/env python
"""
Functions for putting GoCD XML configuration into a canonical format
without changing the semantics.
"""

from collections import defaultdict
from copy import copy
import sys
import lxml.etree as ElementTree

import click


PARSER = ElementTree.XMLParser(
    remove_blank_text=True,
)


def canonicalize(child_sort_key=None):
    """
    Build a canonicalizer function using the specified key to sort
    element children. (Will not sort children if child_sort_key is None).

    Arguments:
        child_sort_key: The key-function to sort element children by
    """
    def canonicalizer(element):
        """
        Canonicalize the supplied GoCD XML Element.

        Arguments:
            element: The etree element to canonicalize.
        """
        canon = copy(element)
        canon.tail = None
        canon[:] = [canonicalize_element(child) for child in canon]
        if child_sort_key is not None:
            canon[:] = sorted(canon, key=child_sort_key)
        return canon
    return canonicalizer


RULES = defaultdict(canonicalize, {
    'admins': canonicalize(lambda ele: ele.text),
    'agents': canonicalize(lambda ele: ele.get('uuid')),
    'artifacts': canonicalize(lambda ele: ele.get('src')),
    'authorization': canonicalize(lambda ele: ele.tag),
    'cruise': canonicalize(lambda ele: (ele.tag, ele.get('group'))),
    'environmentvariables': canonicalize(lambda ele: ele.get('name')),
    'jobs': canonicalize(lambda ele: ele.get('name')),
    'materials': canonicalize(lambda ele: (ele.tag, ele.get('materialName'))),
    'pipelines': canonicalize(lambda ele: (ele.tag, ele.get('name'))),
    'roles': canonicalize(lambda ele: ele.get('name')),
    'security': canonicalize(lambda ele: ele.tag),
    'users': canonicalize(lambda ele: ele.text),
})


def canonicalize_file(input_file, output_file):
    """
    Canonicalize a file and write it to the output.

    Arguments:
        input_file (path or file-like): The file to canonicalize.
        output_file (path or file-like): Where to write the canonicalized configuration.
    """
    input_tree = ElementTree.parse(input_file, parser=PARSER)
    canonicalize_gocd(input_tree).write(output_file, pretty_print=True)
    output_file.flush()


def canonicalize_gocd(config_xml):
    """
    Reformats a GoCD configuration into a diffable format
    that preserves its semantics.

    Arguments:
        config_xml (ElementTree): A GoCD config xml file.

    Returns (ElementTree): A canonicalized GoCD config xml file.
    """
    return ElementTree.ElementTree(canonicalize_element(config_xml.getroot()))


def canonicalize_element(element):
    """
    Canonicalize an element using the standard rule for that elements tag.
    """
    return RULES[element.tag](element)


@click.command()
@click.argument('input_file', nargs=1, type=click.File('rb'))
def cli(input_file):
    """
    Canonicalize a GoCD XML configuration file, and print it to stdout.
    """
    canonicalize_file(input_file, sys.stdout)

if __name__ == '__main__':
    cli()  # pylint: disable=no-value-for-parameter
