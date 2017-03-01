"""
Tests of output XML created by gomatic.
"""

from collections import Counter, namedtuple
import itertools
import os.path
import os
import re

from edxpipelines.utils import ArtifactLocation
import pytest

# pylint: disable=invalid-name

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

    assert required_artifacts <= provided_artifacts, "Missing upstream artifacts (make sure to 'ensure' them)"


def test_upstream_stages(script_result, script_name):
    if script_name in KNOWN_FAILING_PIPELINES:
        pytest.xfail("{} is known to be non-independent".format(script_name))

    Stage = namedtuple('Stage', ['pipeline', 'stage'])

    required_stages = set(
        Stage(
            pipeline_material.get('pipelineName'),
            pipeline_material.get('stageName')
        )
        for materials in script_result.iter('materials')
        for pipeline_material in materials.findall('pipeline')
    )

    provided_stages = set(
        Stage(
            pipeline.get('name'),
            stage.get('name'),
        )
        for pipeline in script_result.iter('pipeline')
        for stage in pipeline.findall('stage')
    )

    assert required_stages <= provided_stages, "Missing upstream stages"


def test_scripts_are_executable(script_name):
    assert os.access(script_name, os.X_OK)


def prefixes(generator):
    """
    Yield all prefixes of a generator. For example:

        list(prefixes("abc")) = ["", "a", "ab", "abc"]
    """
    current_prefix = []
    for item in generator:
        yield list(current_prefix)
        current_prefix.append(item)
    yield current_prefix


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
    if script_name in ['edxpipelines/pipelines/api_deploy.py', 'edxpipelines/pipelines/rollback_asgs.py']:
        pytest.xfail("{} is known to be non-independent".format(script_name))

    RequiredStage = namedtuple('RequiredStage', [
        'downstream_pipeline', 'downstream_stage', 'upstream_pipeline', 'upstream_stage'
    ])

    required_stages = set(
        RequiredStage(
            pipeline.get('name'),
            stage.get('name'),
            fetch.get('pipeline'),
            fetch.get('stage'),
        )
        for pipeline in script_result.iter('pipeline')
        for stage in pipeline.iter('stage')
        for fetch in stage.iter('fetchartifact')
    )

    available_stages = set(
        RequiredStage(
            pipeline.get('name'),
            downstream_stage.get('name'),
            pipeline_material.get('pipelineName'),
            upstream_stage,
        )
        for pipeline in script_result.iter('pipeline')
        for materials in pipeline.iter('materials')
        for pipeline_material in materials.findall('pipeline')
        for upstream_stage in find_available_stages(
            script_result,
            pipeline_material.get('pipelineName'),
            pipeline_material.get('stageName')
        )
        for downstream_stage in pipeline.iter('stage')
    ) | set(
        RequiredStage(
            pipeline.get('name'),
            stage_prefixes[-1].get('name'),
            pipeline.get('name'),
            upstream_stage.get('name'),
        )
        for pipeline in script_result.iter('pipeline')
        for stage_prefixes in prefixes(pipeline.iter('stage'))
        for upstream_stage in stage_prefixes[:-1]
    )

    assert required_stages <= available_stages, "Stages containing artifacts to be fetched aren't upstream"


def test_duplicate_materials(script_result):
    Material = namedtuple('Material', ['pipeline', 'material'])
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

    assert duplicates == set(), "Duplicate material names/destinations"


def test_duplicate_upstream_pipelines(script_result):
    Dependency = namedtuple('PipelineDependency', ['downstream', 'upstream'])
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

    assert duplicates == set(), "Duplicate upstream pipeline dependencies"


def test_duplicate_artifacts(script_result):
    Artifact = namedtuple('Artifact', ['pipeline', 'stage', 'job', 'artifact_dir', 'artifact_name'])
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

    assert duplicates == set(), "Multiple artifacts being fetched to the same path"


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
    if task.get('command') != '/bin/bash' and task[0].text != '-c':
        return

    command = task[1].text

    # Yield numeric variables for all additional arguments
    for index in range(len(task) - 2):
        yield '{}'.format(index)

    # Find all places where we explicitly set bash variables
    for match in re.finditer(r'(^|;)\s*(export )?(?P<var>\w+)=', command, flags=re.IGNORECASE | re.MULTILINE):
        yield match.group('var')

    # Find all bash for-loops
    for match in re.finditer(r'for (?P<var>\w+) in', command, re.IGNORECASE | re.MULTILINE):
        yield match.group('var')


def required_variables_for_task(task):
    """
    Yield all environment variables required by a task.
    """
    if task.get('command') != '/bin/bash' and task[0].text != '-c':
        return

    command = task[1].text

    # Find all $VARIABLE or ${VARIABLE} instances
    for match in re.finditer(
            r'\$(((?P<variable>[^\W{]+))|({(?P<wrappedvar>[^-:=+/?}]+)[-:=+/?]{0,2}[^}]*}))',
            command
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


def environment_variables_provided_by(object):
    """
    Yield all environment variables provided by ``object``.

    Argument:
        object (Element): The element for a pipeline, stage or job
    """
    for env_vars in object.findall('environmentvariables'):
        for variable in env_vars.findall('variable'):
            yield variable.get('name')


def test_environment_variables_defined(script_result, script_name):
    if script_name in ['edxpipelines/pipelines/cd_edxapp.py']:
        pytest.xfail("{} is known to be missing environment variables in test configurations".format(script_name))

    required_environment_variables = set(
        (
            pipeline.get('name'),
            stage.get('name'),
            job.get('name'),
            var,
        )
        for pipeline in script_result.iter('pipeline')
        for stage in pipeline.findall('stage')
        for job in stage.iter('job')
        for task in job.iter('exec')
        for var in required_variables_for_task(task)
    )

    provided_environment_variables = set(
        (
            pipeline.get('name'),
            stage.get('name'),
            job.get('name'),
            var
        )
        for pipeline in script_result.iter('pipeline')
        for stage in pipeline.findall('stage')
        for job in stage.iter('job')
        for var in itertools.chain(
            environment_variables_provided_by(pipeline),
            environment_variables_provided_by(stage),
            environment_variables_provided_by(job),
            (
                var
                for git_material in pipeline.iter('git')
                for var in environment_variables_for_scm_material(git_material)
            ),
            global_environment_variables(),
            (
                var
                for task in job.iter('exec')
                for var in environment_variables_for_task(task)
            ),
        )
    )

    assert required_environment_variables <= provided_environment_variables


def test_unnecessary_material_name(script_result):
    mats_with_unneccesary_name = set(
        (
            pipeline.get('name'),
            material.get('materialName'),
        )
        for pipeline in script_result.iter('pipeline')
        for materials in pipeline.iter('materials')
        for material in materials
        if (
            material.get('dest') and
            material.get('dest') == material.get('materialName') and
            material.get('materialName') not in extract_labeltemplate_vars(pipeline)
        )
    )

    assert mats_with_unneccesary_name == set()


def extract_labeltemplate_vars(pipeline):
    """
    Yield a list of all variables used by the labeltemplate for a pipeline
    """
    labeltemplate = pipeline.get('labeltemplate')
    if labeltemplate is None:
        return

    for match in re.finditer(r'\$\{(?P<var>.*?)(\[.*?\])?\}', labeltemplate):
        var = match.group('var')
        if var != 'COUNT':
            yield var


def test_label_templates(script_result):
    Material = namedtuple('Material', ['pipeline', 'material_name'])
    required_materials = set(
        Material(pipeline.get('name'), var)
        for pipeline in script_result.iter('pipeline')
        for var in extract_labeltemplate_vars(pipeline)
    )

    named_materials = set(
        Material(pipeline.get('name'), material.get('materialName'))
        for pipeline in script_result.iter('pipeline')
        for materials in pipeline.iter('materials')
        for material in materials
        if material.get('materialName')
    )

    assert required_materials <= named_materials, "Missing material names needed by labeltemplates"


def test_defined_roles(script_result):

    available_roles = set(
        role.get('name')
        for security in script_result.iter('security')
        for role in security.iter('role')
    )

    roles_on_groups = set(
        role.text
        for pipeline_group in script_result.iter('pipelines')
        for authorization in pipeline_group.iter('authorization')
        for role in authorization.iter('role')
    )

    assert roles_on_groups <= available_roles
