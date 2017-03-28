#!/usr/bin/env python
"""
Functions for putting GoCD configuration into a canonical format
without changing the semantics.
"""
from collections import defaultdict, namedtuple
import itertools
from pprint import pprint
import sys

import lxml.etree as ElementTree

import click


PARSER = ElementTree.XMLParser(
    remove_blank_text=True,
)


def pipelines(element, pipelines=None):
    only_after = defaultdict(set)
    pipelines_by_name = {
        pipeline.get('name'): pipeline
        for pipeline in element.iter('pipeline')
        if not pipelines or pipeline.get('name') in pipelines
    }
    for pipeline in pipelines_by_name.values():
        for materials in pipeline.iter('materials'):
            for pipeline_material in materials.findall('pipeline'):
                trigger_name = pipeline_material.get('pipelineName')
                only_after[pipeline].add(pipelines_by_name[trigger_name])

    # Split the pipelines into distinct groups (that aren't connected by material dependencies)
    pipeline_groups = {
        pipeline: {pipeline}
        for pipeline in pipelines_by_name.values()
    }

    for pipeline, triggers in only_after.items():
        pipeline_set = pipeline_groups[pipeline]
        for trigger in triggers:
            trigger_set = pipeline_groups[trigger]

            # If the pipeline and trigger are already grouped, skip
            if pipeline_set is trigger_set:
                continue

            # Otherwise, merge the pipeline and trigger groups
            pipeline_set.update(trigger_set)
            for item in trigger_set:
                pipeline_groups[item] = pipeline_set

    groups = []
    # Inside each independent group, group the pipelines into phases
    for group in set(tuple(group) for group in pipeline_groups.values()):
        phases = []
        group = set(group)

        while group:
            # Find all pipelines with no incoming dependencies
            phase = []
            for pipeline in group:
                if pipeline in only_after:
                    continue
                phase.append(pipeline)

            # Record the phase
            phases.append(Concurrent(
                None,
                sum(
                    [
                        simplify_element(pipeline)
                        for pipeline in phase
                    ],
                    []
                )
            ))
            group -= set(phase)

            # Remove pipelines from all other dependency lists
            for pipeline in phase:
                for after in only_after.keys():
                    triggers = only_after[after]
                    triggers.discard(pipeline)
                    if not triggers:
                        del only_after[after]

        groups.append(Serial(None, phases))
    return [Concurrent(None, groups)]


def approval(element, pipelines=None):
    if element.get('type') == "manual":
        return "block on manual approval"

def indent(blocks, indent):
    indented = []
    for block in blocks:
        lines = block.split('\n')
        indented.append("\n".join(indent + line for line in lines))
    return "\n".join(indented)


def sort_key(task):
    if task.element:
        return (task.element.tag, task.element.get('name'))
    elif task.tasks:
        if task.sorted:
            return sort_key(sorted(task.tasks, key=sort_key)[0])
        else:
            return sort_key(task.tasks[0])
    else:
        return None


class Container(namedtuple('_Container', ['element', 'tasks'])):
    sorted = False

    def render(self, current_mode=None, context=()):
        new_context = False
        if self.element and self.element.get('name'):
            context += (self.element.get('name'),)
            new_context = True

        if len(self.tasks) == 1 and isinstance(self.tasks[0], Container):
            return self.tasks[0].render(current_mode, context)

        if self.sorted:
            tasks = sorted(self.tasks, key=sort_key)
        else:
            tasks = self.tasks

        rendered_tasks = []
        for task in tasks:
            rendered_tasks.append(task.render(self.__class__, context))
        rendered_tasks = [
            rendered
            for rendered in rendered_tasks
            if rendered
        ]

        if current_mode == self.__class__:
            if new_context:
                return ['start {}'.format(
                    ' :: '.join(context),
                )] + sum(rendered_tasks, []) + ['end {}'.format(
                    ' :: '.join(context),
                )]
            else:
                return sum(rendered_tasks, [])
        else:
            if new_context:
                return [
                    '{}  # {}'.format(
                        self.__class__.__name__,
                        ' :: '.join(context),
                    )
                ] + [
                    '    {}'.format(task)
                    for rendered in rendered_tasks
                    for task in rendered
                ]
            else:
                return [
                    self.__class__.__name__,
                ] + [
                    '    {}'.format(task)
                    for rendered in rendered_tasks
                    for task in rendered
                ]

    @classmethod
    def process(cls, element, pipelines=None):
        return [cls(element, sum([simplify_element(child) for child in element], []))]


class Serial(Container):
    sorted = False

class Concurrent(Container):
    sorted = True


def recurse(element, pipelines=None):
    return sum(
        (simplify_element(child) for child in element),
        []
    )


class Exec(namedtuple('_Exec', ['element'])):
    @property
    def tasks(self):
        return [self]

    def render(self, current_mode=None, context=()):
        runif = self.element.find('runif')
        if runif and runif.get('status', 'passed') != 'passed':
            runif_string = "when {}".format(runif.get('status'))
        else:
            runif_string = ''
        return ["{}{}".format(
            runif_string,
            " ".join([self.element.get('command')] + [arg.text for arg in self.element.findall('arg')])
        )]

    @classmethod
    def process(cls, element, pipelines=None):
        return [cls(element)]

RULES = defaultdict(lambda: recurse, {
    'cruise': pipelines,
    'pipeline': Serial.process,
    'stage': Concurrent.process,
    'job': Serial.process,
    'exec': Exec.process,
})

def simplify_file(input_file, output_file, pipelines=None):
    """
    Simplify a file to its essential topology and write it to the output.

    Arguments:
        input_file (path or file-like): The file to simplify.
        output_file (path or file-like): Where to write the simplified configuration.
    """
    input_tree = ElementTree.parse(input_file, parser=PARSER)
    output_file.write("\n".join(simplify_gocd(input_tree, pipelines).render()))


def simplify_gocd(config_xml, pipelines=None):
    """
    Reformats a GoCD configuration into a diffable format
    that preserves its topology (concurrency of tasks).

    Arguments:
        config_xml (ElementTree): A GoCD config xml file.

    Returns (ElementTree): A simplified GoCD config file.
    """
    return Concurrent(config_xml.getroot(), simplify_element(config_xml.getroot(), pipelines))


def simplify_element(element, pipelines=None):
    """
    Simplify an element using the standard rule for that elements tag.
    """
    return RULES[element.tag](element, pipelines=pipelines)


@click.command()
@click.argument('input_file', nargs=1, type=click.File('rb'))
@click.option('--pipeline', multiple=True, help="A pipeline to limit the topology computation to")
def cli(input_file, pipeline):
    """
    simplify a GoCD XML configuration file, and print it to stdout.
    """
    simplify_file(input_file, sys.stdout, pipelines=set(pipeline))


if __name__ == '__main__':
    cli()  # pylint: disable=no-value-for-parameter