#!/usr/bin/env python
from functools import partial
import sys
from os import path
from gomatic import *

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

from edxpipelines import utils
from edxpipelines.patterns import stages
from edxpipelines.patterns import tasks
from edxpipelines.patterns import pipelines
from edxpipelines import constants
from edxpipelines.materials import (
    TUBULAR, CONFIGURATION, EDX_PLATFORM, EDX_SECURE, EDGE_SECURE,
    EDX_MICROSITE, EDX_INTERNAL, EDGE_INTERNAL
)


def cut_branch(edxapp_group, config):
    """
    Variables needed for this pipeline:
    - git_token
    """
    pipeline = edxapp_group.ensure_replacement_of_pipeline('edxapp_cut_release_candidate')

    edx_platform_master = EDX_PLATFORM(branch="master", ignore_patterns=[])
    pipeline.ensure_material(edx_platform_master)
    pipeline.ensure_material(TUBULAR())

    stages.generate_create_branch(
        pipeline,
        constants.GIT_CREATE_BRANCH_STAGE_NAME,
        'edx',
        'edx-platform',
        EDX_PLATFORM().branch,
        config['git_token'],
        manual_approval=True,
        sha='$GO_REVISION_{}'.format(edx_platform_master.material_name.replace('-', '_').upper()),
    )
    pipeline.set_timer('0 0/5 15-18 ? * MON-FRI', True)

    return pipeline


def prerelease_materials(edxapp_group, config):
    """
    Variables needed for this pipeline:
    - gocd_username
    - gocd_password
    - gocd_url
    - configuration_secure_repo
    - hipchat_token
    - github_private_key
    - aws_access_key_id
    - aws_secret_access_key
    - ec2_vpc_subnet_id
    - ec2_security_group_id

    - ec2_instance_profile_name
    - base_ami_id

    Optional variables:
    - configuration_secure_version
    """
    pipeline = edxapp_group.ensure_replacement_of_pipeline("prerelease_edxapp_materials_latest")

    for material in (
            CONFIGURATION, EDX_SECURE, EDGE_SECURE,
            EDX_MICROSITE, EDX_INTERNAL, EDGE_INTERNAL, EDX_PLATFORM,
    ):
        pipeline.ensure_material(material(ignore_patterns=[]))

    pipeline.ensure_material(TUBULAR())

    stages.generate_armed_stage(pipeline, constants.ARM_PRERELEASE_STAGE)

    return pipeline


def build_migrate_deploy_subset_pipeline(
        pipeline_group, stage_builders, config,
        pipeline_name, ami_artifact=None, auto_run=False,
        post_cleanup_builders=None):
    """
    Arguments:
        ami_artifact (ArtifactLocation): The ami to use to launch the
            instances on. If None, select that ami based on the
            edx_deployment and edx_environment.

    Variables needed for this pipeline:
    - aws_access_key_id
    - aws_secret_access_key
    - ec2_vpc_subnet_id
    - ec2_security_group_id
    - ec2_instance_profile_name
    - base_ami_id

    Optional variables:
    - configuration_secure_version
    - configuration_internal_version
    """
    pipeline = pipeline_group.ensure_replacement_of_pipeline(pipeline_name)

    base_ami_id = config.get('base_ami_id')

    # We always need to launch the AMI, independent deploys are done with a different pipeline
    # if the pipeline has a migrate stage, but no building stages, look up the build information from the
    # upstream pipeline.
    if ami_artifact is None:
        stages.generate_base_ami_selection(
            pipeline,
            config['aws_access_key_id'],
            config['aws_secret_access_key'],
            config['play_name'],
            config['edx_deployment'],
            config['edx_environment'],
            base_ami_id
        )
        ami_artifact = utils.ArtifactLocation(
            pipeline.name,
            constants.BASE_AMI_SELECTION_STAGE_NAME,
            constants.BASE_AMI_SELECTION_JOB_NAME,
            FetchArtifactFile(constants.BASE_AMI_OVERRIDE_FILENAME),
        )

    launch_stage = stages.generate_launch_instance(
        pipeline,
        config['aws_access_key_id'],
        config['aws_secret_access_key'],
        config['ec2_vpc_subnet_id'],
        config['ec2_security_group_id'],
        config['ec2_instance_profile_name'],
        base_ami_id,
        upstream_build_artifact=ami_artifact,
        manual_approval=not auto_run
    )

    # Generate all the requested stages
    for builder in stage_builders:
        builder(pipeline, config)

    # Add the cleanup stage
    generate_cleanup_stages(pipeline, config, launch_stage)

    if post_cleanup_builders:
        for builder in post_cleanup_builders:
            builder(pipeline, config)

    return pipeline


def generate_build_stages(app_repo, theme_url, configuration_secure_repo,
                          configuration_internal_repo, configuration_url):
    def builder(pipeline, config):
        stages.generate_run_play(
            pipeline,
            'playbooks/edx-east/edxapp.yml',
            play=config['play_name'],
            deployment=config['edx_deployment'],
            edx_environment=config['edx_environment'],
            private_github_key=config['github_private_key'],
            app_repo=app_repo,
            configuration_secure_dir='{}-secure'.format(config['edx_deployment']),
            configuration_internal_dir='{}-internal'.format(config['edx_deployment']),
            hipchat_token=config['hipchat_token'],
            hipchat_room='release',
            edx_platform_version='$GO_REVISION_EDX_PLATFORM',
            edx_platform_repo='$APP_REPO',
            configuration_version='$GO_REVISION_CONFIGURATION',
            edxapp_theme_source_repo=theme_url,
            edxapp_theme_version='$GO_REVISION_EDX_THEME',
            edxapp_theme_name='$EDXAPP_THEME_NAME',
            disable_edx_services='true',
            COMMON_TAG_EC2_INSTANCE='true',
            cache_id='$GO_PIPELINE_COUNTER'
        )

        stages.generate_create_ami_from_instance(
            pipeline,
            play=config['play_name'],
            deployment=config['edx_deployment'],
            edx_environment=config['edx_environment'],
            app_repo=app_repo,
            app_version='$GO_REVISION_EDX_PLATFORM',
            configuration_secure_repo=configuration_secure_repo,
            configuration_internal_repo=configuration_internal_repo,
            configuration_repo=configuration_url,
            hipchat_token=config['hipchat_token'],
            hipchat_room='release pipeline',
            configuration_version='$GO_REVISION_CONFIGURATION',
            configuration_secure_version='$GO_REVISION_{}_SECURE'.format(config['edx_deployment'].upper()),
            configuration_internal_version='$GO_REVISION_{}_SECURE'.format(config['edx_deployment'].upper()),
            aws_access_key_id=config['aws_access_key_id'],
            aws_secret_access_key=config['aws_secret_access_key'],
            edxapp_theme_source_repo=theme_url,
            edxapp_theme_version='$GO_REVISION_EDX_MICROSITE',
        )

        return pipeline
    return builder


def generate_migrate_stages(pipeline, config):
    #
    # Create the DB migration running stage.
    #
    ansible_inventory_location = utils.ArtifactLocation(
        pipeline.name,
        constants.LAUNCH_INSTANCE_STAGE_NAME,
        constants.LAUNCH_INSTANCE_JOB_NAME,
        'ansible_inventory'
    )
    instance_ssh_key_location = utils.ArtifactLocation(
        pipeline.name,
        constants.LAUNCH_INSTANCE_STAGE_NAME,
        constants.LAUNCH_INSTANCE_JOB_NAME,
        'key.pem'
    )
    launch_info_location = utils.ArtifactLocation(
        pipeline.name,
        constants.LAUNCH_INSTANCE_STAGE_NAME,
        constants.LAUNCH_INSTANCE_JOB_NAME,
        constants.LAUNCH_INSTANCE_FILENAME
    )
    # Check the migration duration on the stage environment only.
    if pipeline.name.startswith('STAGE'):
        duration_threshold = config['migration_duration_threshold']
    else:
        duration_threshold = None

    for sub_app in config['edxapp_subapps']:
        stages.generate_run_migrations(
            pipeline,
            db_migration_pass=config['db_migration_pass'],
            inventory_location=ansible_inventory_location,
            instance_key_location=instance_ssh_key_location,
            launch_info_location=launch_info_location,
            application_user=config['db_migration_user'],
            application_name=config['play_name'],
            application_path=config['application_path'],
            sub_application_name=sub_app,
            duration_threshold=duration_threshold,
            from_address=config['alert_from_address'],
            to_addresses=config['alert_to_addresses']
        )

    return pipeline


def generate_deploy_stages(pipeline_name_build, auto_deploy_ami=False):
    #
    # Create the stage to deploy the AMI.
    #
    def builder(pipeline, config):
        built_ami_file_location = utils.ArtifactLocation(
            pipeline_name_build,
            constants.BUILD_AMI_STAGE_NAME,
            constants.BUILD_AMI_JOB_NAME,
            constants.BUILD_AMI_FILENAME,
        )
        stages.generate_deploy_ami(
            pipeline,
            config['asgard_api_endpoints'],
            config['asgard_token'],
            config['aws_access_key_id'],
            config['aws_secret_access_key'],
            built_ami_file_location,
            manual_approval=not auto_deploy_ami
        )

        base_ami_file_location = utils.ArtifactLocation(
            pipeline_name_build,
            constants.BASE_AMI_SELECTION_STAGE_NAME,
            constants.BASE_AMI_SELECTION_JOB_NAME,
            constants.BASE_AMI_OVERRIDE_FILENAME
        )

        pipeline.ensure_unencrypted_secure_environment_variables({'GITHUB_TOKEN': config['github_token']})
        stages.generate_message_prs(
            pipeline,
            'edx',
            'edx-platform',
            '$GITHUB_TOKEN',
            '$GO_REVISION_EDX_PLATFORM',
            config['edx_environment'],
            base_ami_artifact=base_ami_file_location,
            ami_tag_app='edx_platform',
        )
        return pipeline
    return builder


def generate_cleanup_stages(pipeline, config, launch_stage):
    #
    # Create the stage to terminate the EC2 instance used to both build the AMI and run DB migrations.
    #
    instance_info_location = utils.ArtifactLocation(
        pipeline.name,
        launch_stage.name,
        constants.LAUNCH_INSTANCE_JOB_NAME,
        constants.LAUNCH_INSTANCE_FILENAME
    )
    stages.generate_terminate_instance(
        pipeline,
        instance_info_location,
        aws_access_key_id=config['aws_access_key_id'],
        aws_secret_access_key=config['aws_secret_access_key'],
        hipchat_token=config['hipchat_token'],
        runif='any'
    )
    return pipeline


def manual_verification(edxapp_deploy_group, config):
    """
    Variables needed for this pipeline:
    materials: A list of dictionaries of the materials used in this pipeline
    upstream_pipelines: a list of dictionaries of the upstream pipelines that feed in to the manual verification
    """
    pipeline = edxapp_deploy_group.ensure_replacement_of_pipeline("manual_verification_edxapp_prod_early_ami_build")

    for material in (
        TUBULAR, CONFIGURATION, EDX_PLATFORM, EDX_SECURE, EDGE_SECURE,
        EDX_MICROSITE, EDX_INTERNAL, EDGE_INTERNAL
    ):
        pipeline.ensure_material(material())

    # What this accomplishes:
    # When a pipeline such as edx stage runs this pipeline is downstream. Since the first stage is automatic
    # the git materials will be carried over from the first pipeline.
    #
    # The second stage in this pipeline requires manual approval.
    #
    # This allows the overall workflow to remain paused while manual verification is completed and allows the git
    # materials to stay pinned.
    #
    # Once the second phase is approved, the workflow will continue and pipelines downstream will continue to execute
    # with the same pinned materials from the upstream pipeline.
    stages.generate_armed_stage(pipeline, constants.INITIAL_VERIFICATION_STAGE_NAME)

    manual_verification_stage = pipeline.ensure_stage(constants.MANUAL_VERIFICATION_STAGE_NAME)
    manual_verification_stage.set_has_manual_approval()
    manual_verification_job = manual_verification_stage.ensure_job(constants.MANUAL_VERIFICATION_JOB_NAME)
    manual_verification_job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                'echo Manual Verification run number $GO_PIPELINE_COUNTER completed by $GO_TRIGGER_USER'
            ],
        )
    )

    return pipeline


def generate_e2e_test_stage(pipeline, config):
    # For now, you can only trigger builds on a single jenkins server, because you can only
    # define a single username/token.
    # And all the jobs that you want to trigger need the same job token defined.
    # TODO: refactor when required so that each job can define their own user and job tokens
    pipeline.ensure_unencrypted_secure_environment_variables(
        {
            'JENKINS_USER_TOKEN': config['jenkins_user_token'],
            'JENKINS_JOB_TOKEN': config['jenkins_job_token']
        }
    )

    # Create the stage with the Jenkins jobs
    jenkins_stage = pipeline.ensure_stage(constants.JENKINS_VERIFICATION_STAGE_NAME)
    jenkins_user_name = config['jenkins_user_name']

    jenkins_url = "https://build.testeng.edx.org"

    e2e_tests = jenkins_stage.ensure_job('edx-e2e-test')
    tasks.generate_package_install(e2e_tests, 'tubular')
    tasks.trigger_jenkins_build(
        e2e_tests,
        jenkins_url,
        jenkins_user_name,
        'edx-e2e-tests',
        {},
        timeout=60 * 60,
    )

    microsites_tests = jenkins_stage.ensure_job('microsites-staging-tests')
    tasks.generate_package_install(microsites_tests, 'tubular')
    tasks.trigger_jenkins_build(
        microsites_tests,
        jenkins_url,
        jenkins_user_name,
        'microsites-staging-tests', {
            'CI_BRANCH': 'kashif/white_label',
        },
        timeout=60 * 60,
    )


def rollback_asgs(edxapp_deploy_group, pipeline_name, build_pipeline, deploy_pipeline, config):
    """
    Arguments:
        edxapp_deploy_group (gomatic.PipelineGroup): The group in which to create this pipeline
        pipeline_name (str): The name of this pipeline
        deploy_pipeline (gomatic.Pipeline): The pipeline to retrieve the ami_deploy_info.yml artifact from

    Configuration Required:
        tubular_sleep_wait_time
        asgard_api_endpoints
        asgard_token
        aws_access_key_id
        aws_secret_access_key
        hipchat_token
    """
    pipeline = edxapp_deploy_group.ensure_replacement_of_pipeline(pipeline_name)\
                                  .ensure_environment_variables({'WAIT_SLEEP_TIME': config['tubular_sleep_wait_time']})

    for material in (
        TUBULAR, CONFIGURATION, EDX_PLATFORM, EDX_SECURE, EDGE_SECURE,
        EDX_MICROSITE, EDX_INTERNAL, EDGE_INTERNAL,
    ):
        pipeline.ensure_material(material())

    # Specify the upstream deploy pipeline material for this rollback pipeline.
    # Assumes there's only a single upstream pipeline material for this pipeline.
    pipeline.ensure_material(
        PipelineMaterial(
            pipeline_name=deploy_pipeline.name,
            stage_name=constants.DEPLOY_AMI_STAGE_NAME,
            material_name='deploy_pipeline',
        )
    )

    # Specify the artifact that will be fetched containing the previous deployment information.
    deploy_file_location = utils.ArtifactLocation(
        deploy_pipeline.name,
        constants.DEPLOY_AMI_STAGE_NAME,
        constants.DEPLOY_AMI_JOB_NAME,
        constants.DEPLOY_AMI_OUT_FILENAME,
    )

    # Create the armed stage as this pipeline needs to auto-execute
    stages.generate_armed_stage(pipeline, constants.ARMED_JOB_NAME)

    # Create a single stage in the pipeline which will rollback to the previous ASGs/AMI.
    rollback_stage = stages.generate_rollback_asg_stage(
        pipeline,
        config['asgard_api_endpoints'],
        config['asgard_token'],
        config['aws_access_key_id'],
        config['aws_secret_access_key'],
        config['hipchat_token'],
        constants.HIPCHAT_ROOM,
        deploy_file_location,
    )
    # Since we only want this stage to rollback via manual approval, ensure that it is set on this stage.
    rollback_stage.set_has_manual_approval()

    base_ami_file_location = utils.ArtifactLocation(
        build_pipeline.name,
        constants.BASE_AMI_SELECTION_STAGE_NAME,
        constants.BASE_AMI_SELECTION_JOB_NAME,
        constants.BASE_AMI_OVERRIDE_FILENAME
    )

    # We need the build_pipeline upstream so that we can fetch the artifact from it
    pipeline.ensure_material(
        PipelineMaterial(
            pipeline_name=build_pipeline.name,
            stage_name=constants.BASE_AMI_SELECTION_STAGE_NAME,
            material_name='select_base_ami',
        )
    )

    # Message PRs being rolled back
    pipeline.ensure_unencrypted_secure_environment_variables({'GITHUB_TOKEN': config['github_token']})
    stages.generate_message_prs(
        pipeline,
        'edx',
        'edx-platform',
        '$GITHUB_TOKEN',
        '$GO_REVISION_EDX_PLATFORM',
        'rollback',
        base_ami_artifact=base_ami_file_location,
        ami_tag_app='edx_platform',
    )

    return pipeline


def merge_back_branches(edxapp_deploy_group, pipeline_name, deploy_artifact, config):
    """
    Arguments:
        edxapp_deploy_group (gomatic.PipelineGroup): The group in which to create this pipeline
        pipeline_name (str): The name of this pipeline
        deploy_pipeline_name (str): The name of the deploy pipeline from which to fetch an artifact.

    Configuration Required:
        github_org
        github_repo
        rc_branch
        release_branch
        release_to_master_branch
        master_branch
        github_token
    """
    pipeline = edxapp_deploy_group.ensure_replacement_of_pipeline(pipeline_name)

    for material in (
        TUBULAR, CONFIGURATION, EDX_PLATFORM, EDX_SECURE, EDGE_SECURE,
        EDX_MICROSITE, EDX_INTERNAL, EDGE_INTERNAL
    ):
        pipeline.ensure_material(material())

    # Create a single stage in the pipeline which will:
    #   - merge the RC branch into the release branch
    #   - tag the release branch
    stages.generate_merge_branch_and_tag(
        pipeline,
        constants.GIT_MERGE_RC_BRANCH_STAGE_NAME,
        deploy_artifact,
        org=config['github_org'],
        repo=config['github_repo'],
        target_branch=config['release_branch'],
        head_sha='$GO_REVISION_EDX_PLATFORM',
        token=config['github_token'],
        fast_forward_only=True,
        manual_approval=False
    )

    # Create a single stage in the pipeline which will:
    #  - create a branch off the HEAD of release
    #  - create a PR to merge release into master
    stages.generate_create_branch_and_pr(
        pipeline,
        constants.CREATE_MASTER_MERGE_PR_STAGE_NAME,
        org=config['github_org'],
        repo=config['github_repo'],
        source_branch=config['release_branch'],
        new_branch=config['release_to_master_branch'],
        target_branch=config['master_branch'],
        pr_title='Merge release back to master',
        pr_body='Merge the release branch back to master via a temporary branch off release.',
        token=config['github_token'],
        manual_approval=False
    )

    # Create a single stage in the pipeline which will:
    #   - poll for successful completion of PR tests
    #   - merge the PR
    stages.generate_poll_tests_and_merge_pr(
        pipeline,
        constants.CHECK_PR_TESTS_AND_MERGE_STAGE_NAME,
        org=config['github_org'],
        repo=config['github_repo'],
        token=config['github_token'],
        initial_poll_wait=config['initial_poll_wait'],
        max_poll_tries=config['max_poll_tries'],
        poll_interval=config['poll_interval'],
        manual_approval=False
    )

    return pipeline
