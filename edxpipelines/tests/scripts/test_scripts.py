"""
Tests of output XML created by gomatic.
"""

from collections import Counter, namedtuple
import os.path
import os

from edxpipelines.utils import ArtifactLocation
import pytest

KNOWN_FAILING_PIPELINES = [
    'edxpipelines/pipelines/api_deploy.py',
    'edxpipelines/pipelines/rollback_asgs.py'
]


def test_upstream_artifacts(script_result, script_name):
    if script_name in KNOWN_FAILING_PIPELINES:
        pytest.xfail("{} is known to be non-independent".format(script_name))

    required_artifacts = set(
        ArtifactLocation(
            pipeline=fetch.get('pipeline'),
            stage=fetch.get('stage'),
            job=fetch.get('job'),
            file_name=fetch.get('srcfile', fetch.get('srcdir')),
        )
        for fetch in script_result.iter('fetchartifact')
    )

    provided_artifacts = set(
        ArtifactLocation(
            pipeline=pipeline.get('name'),
            stage=stage.get('name'),
            job=job.get('name'),
            file_name=os.path.basename(artifact.get('src')),
        )
        for pipeline in script_result.iter('pipeline')
        for stage in pipeline.findall('stage')
        for job in stage.iter('job')
        for artifact in job.iter('artifact')
    )

    assert required_artifacts - provided_artifacts == set([])


def test_upstream_stages(script_result, script_name):
    if script_name in KNOWN_FAILING_PIPELINES:
        pytest.xfail("{} is known to be non-independent".format(script_name))

    required_stages = set(
        (
            pipeline_material.get('pipelineName'),
            pipeline_material.get('stageName')
        )
        for materials in script_result.iter('materials')
        for pipeline_material in materials.findall('pipeline')
    )

    provided_stages = set(
        (
            pipeline.get('name'),
            stage.get('name'),
        )
        for pipeline in script_result.iter('pipeline')
        for stage in pipeline.findall('stage')
    )

    assert required_stages - provided_stages == set([])


def test_scripts_are_executable(script_name):
    assert os.access(script_name, os.X_OK)


def find_available_stages(script_result, target_pipeline, target_stage):
    """
    Yields the names of all stages inside ``target_pipeline`` that are available
    by depending on ``target_stage``.
    """
    for pipeline in script_result.iter('pipeline'):
        if pipeline.get('name') != target_pipeline:
            continue

        for stage in pipeline.iter('stage'):
            stage_name = stage.get('name')
            yield stage_name
            if stage_name == target_stage:
                return


def test_upstream_stages_for_artifacts(script_result, script_name):
    if script_name in ['edxpipelines/pipelines/api_deploy.py']:
        pytest.xfail("{} is known to be non-independent".format(script_name))

    required_artifacts = set(
        (
            pipeline.get('name'),  # This pipeline
            fetch.get('pipeline'),  # The upstream pipeline
            fetch.get('stage'),  # The upstream stage
        )
        for pipeline in script_result.iter('pipeline')
        for fetch in pipeline.iter('fetchartifact')
        if fetch.get('pipeline') != pipeline.get('name')
    )

    available_stages = set(
        (
            pipeline.get('name'),  # This pipeline
            pipeline_material.get('pipelineName'),  # The upstream pipeline
            stage,  # The upstream stage
        )
        for pipeline in script_result.iter('pipeline')
        for materials in pipeline.iter('materials')
        for pipeline_material in materials.findall('pipeline')
        for stage in find_available_stages(
            script_result,
            pipeline_material.get('pipelineName'),
            pipeline_material.get('stageName')
        ),
    )

    assert required_artifacts - available_stages == set([])


def test_duplicate_materials(script_result):
    Material = namedtuple('Material', ['pipeline', 'material'])  # pylint: disable=invalid-name
    material_counts = Counter(
        Material(pipeline.get('name'), material.get('materialName'))
        for pipeline in script_result.iter('pipeline')
        for materials in pipeline.iter('materials')
        for material in materials
    )

    duplicates = set(
        material_id
        for material_id, count
        in material_counts.items()
        if count > 1
    )

    assert duplicates == set()


def test_duplicate_upstream_pipelines(script_result):
    Dependency = namedtuple('PipelineDependency', ['downstream', 'upstream'])  # pylint: disable=invalid-name
    material_counts = Counter(
        Dependency(pipeline.get('name'), pipeline_material.get('pipelineName'))
        for pipeline in script_result.iter('pipeline')
        for materials in pipeline.iter('materials')
        for pipeline_material in materials.findall('pipeline')
    )

    duplicates = set(
        material_id
        for material_id, count
        in material_counts.items()
        if count > 1
    )

    assert duplicates == set()
