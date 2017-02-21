"""
Tests of output XML created by gomatic.
"""

from collections import Counter, namedtuple
import os.path
import os
import re

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
        Material(pipeline.get('name'), material.get('materialName', material.get('dest')))
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


def test_duplicate_artifacts(script_result):
    Artifact = namedtuple('Artifact', ['pipeline', 'stage', 'job', 'artifact_dir', 'artifact_name'])  # pylint: disable=invalid-name
    artifact_counts = Counter(
        Artifact(
            pipeline.get('name'),
            stage.get('name'),
            job.get('name'),
            fetch.get('dest'),
            fetch.get('srcfile', fetch.get('srcdir'))
        )
        for pipeline in script_result.iter('pipeline')
        for stage in pipeline.findall('stage')
        for job in stage.iter('job')
        for fetch in job.iter('fetchartifact')
    )

    duplicates = set(
        artifact_id
        for artifact_id, count
        in artifact_counts.items()
        if count > 1
    )

    assert duplicates == set()


def environment_variables_for_scm_material(material):
    """
    Yield all environment variables exposed to jobs by SCM materials.
    """
    # pylint: disable=line-too-long
    # This logic mirrors: https://github.com/gocd/gocd/blob/3cfb0a62fccabcc9e345df39cbede86c6cbea6db/domain/src/com/thoughtworks/go/config/materials/ScmMaterial.java#L141
    mat_name = material.get('materialName', material.get('dest'))

    if mat_name is None:
        mat_name = ""
    else:
        mat_name = '_{}'.format(re.sub("[^A-Za-z0-9_]", "_", mat_name.upper()))

    yield "GO_REVISION{}".format(mat_name)
    yield "GO_TO_REVISION{}".format(mat_name)
    yield "GO_FROM_REVISION{}".format(mat_name)


def environment_variables_for_task(task):
    """
    Yield all environment variables exposed by a task.
    """
    if task.get('command') != '/bin/bash':
        return

    text = " ".join(arg.text for arg in task.iter('arg'))
    # Find all places where we explicitly set bash variables
    for match in re.finditer(r'(export )?(?P<var>\w+)=', text, flags=re.IGNORECASE):
        yield match.group('var')

    # Find all bash for-loops
    for match in re.finditer(r'for (?P<var>\w+) in', text, re.IGNORECASE):
        yield match.group('var')


def required_variables_for_task(task):
    """
    Yield all environment variables required by a task.
    """
    if task.get('command') != '/bin/bash':
        return

    for arg in task.iter('arg'):
        # Find all $VARIABLE or ${VARIABLE} instances
        for match in re.finditer(
                r'\$(((?P<variable>[^\W{]+))|({(?P<wrappedvar>[^-:=+/?}]+)[-:=+/?]{0,2}[^}]*}))',
                arg.text
        ):
            yield match.group('variable') or match.group('wrappedvar')


def global_environment_variables():
    """
    Yield all global environment variables.
    """
    yield 'GO_PIPELINE_COUNTER'
    yield 'GO_PIPELINE_LABEL'
    yield 'GO_PIPELINE_NAME'
    yield 'GO_SERVER_URL'
    yield 'GO_STAGE_COUNTER'
    yield 'GO_STAGE_NAME'
    yield 'GO_TRIGGER_USER'
    yield 'PRIVATE_KEY'


def test_environment_variables_defined(script_result, script_name):
    if script_name in ['edxpipelines/pipelines/cd_edxapp.py']:
        pytest.xfail("{} is known to be missing environment variables in test configurations".format(script_name))

    required_environment_variables = set(
        (
            pipeline.get('name'),
            var,
        )
        for pipeline in script_result.iter('pipeline')
        for stage in pipeline.findall('stage')
        for job in stage.iter('job')
        for task in job.iter('exec')
        for var in required_variables_for_task(task)
    )

    provided_environment_variables = set(
        (pipeline.get('name'), var.get('name'))
        for pipeline in script_result.iter('pipeline')
        for var in pipeline.iter('variable')
    ) | set(
        (pipeline.get('name'), var)
        for pipeline in script_result.iter('pipeline')
        for git_material in pipeline.iter('git')
        for var in environment_variables_for_scm_material(git_material)
    ) | set(
        (pipeline.get('name'), var)
        for pipeline in script_result.iter('pipeline')
        for var in global_environment_variables()
    ) | set(
        (pipeline.get('name'), var)
        for pipeline in script_result.iter('pipeline')
        for stage in pipeline.findall('stage')
        for job in stage.iter('job')
        for task in job.iter('exec')
        for var in environment_variables_for_task(task)
    )

    assert required_environment_variables - provided_environment_variables == set()


def test_unnecessary_material_name(script_result):
    mats_with_unneccesary_name = set(
        (
            pipeline.get('name'),
            material.get('materialName'),
        )
        for pipeline in script_result.iter('pipeline')
        for materials in pipeline.iter('materials')
        for material in materials
        if material.get('dest') and material.get('dest') == material.get('materialName')
    )

    message = (
        "The following materials specify 'materialName', but don't "
        "need to, because it is the same as 'dest':\n{}"
    ).format(
        "\n".join("    Pipeline: {}, material: {}".format(*mat) for mat in sorted(mats_with_unneccesary_name))
    )
    assert mats_with_unneccesary_name == set(), message
