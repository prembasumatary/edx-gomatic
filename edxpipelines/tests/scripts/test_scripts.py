import os.path
from edxpipelines.utils import ArtifactLocation


def test_upstream_artifacts(script_result):
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


def test_upstream_stages(script_result):
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
