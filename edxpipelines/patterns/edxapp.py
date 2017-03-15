#!/usr/bin/env python

"""
Gomatic patterns for building the edxapp pipeline.
"""

import sys
from os import path
from gomatic import ExecTask, PipelineMaterial

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

# pylint: disable=wrong-import-position
from edxpipelines import utils
from edxpipelines.patterns import stages, jobs, tasks
from edxpipelines.patterns.tasks import private_releases
from edxpipelines import constants
from edxpipelines.materials import (
    TUBULAR, CONFIGURATION, EDX_PLATFORM, EDX_SECURE, EDGE_SECURE,
    EDX_MICROSITE, EDX_INTERNAL, EDGE_INTERNAL, EDX_PLATFORM_PRIVATE,
)


EDXAPP_SUBAPPS = ['cms', 'lms']

# This pipeline contains the manual stage that gates a production deploy.
# That stage is automatically advanced by a separate release-advancing pipeline
# to trigger a production deployment.
EDXAPP_MANUAL_PIPELINE_NAME = "manual_verification_edxapp_prod_early_ami_build"


def make_release_candidate(edxapp_group, config):
    """
    Variables needed for this pipeline:
    - git_token
    """
    pipeline = edxapp_group.ensure_replacement_of_pipeline('edxapp_cut_release_candidate')

    edx_platform_master = EDX_PLATFORM(material_name='edx-platform', branch="master", ignore_patterns=[])
    pipeline.ensure_material(edx_platform_master)
    pipeline.ensure_material(TUBULAR())
    stage = pipeline.ensure_stage(constants.MAKE_RELEASE_CANDIDATE_STAGE_NAME)
    job = stage.ensure_job(constants.MAKE_RELEASE_CANDIDATE_JOB_NAME)
    tasks.generate_package_install(job, 'tubular')

    tasks.generate_merge_branch(
        pipeline,
        job,
        config['git_token'],
        'edx',
        'edx-platform',
        "origin/{}".format(edx_platform_master.branch),
        EDX_PLATFORM().branch,
        fast_forward_only=True,
        reference_repo='edx-platform',
    )

    # These two options together make sure that the pipeline only triggers
    # from the timer trigger.
    pipeline.set_timer('0 0/5 15-18 ? * MON-FRI', only_on_changes=True)
    stage.set_has_manual_approval()

    return pipeline


def release_advancer(edxapp_group, config):
    """
    Variables needed for this pipeline:
    - gocd_username
    - gocd_password
    - gocd_url
    - hipchat_token
    """
    pipeline = edxapp_group.ensure_replacement_of_pipeline("edxapp_release_advancer")
    pipeline.set_label_template('${COUNT}')

    pipeline.ensure_material(TUBULAR(material_name='tubular'))

    stage = stages.generate_find_and_advance_release(
        pipeline,
        EDXAPP_MANUAL_PIPELINE_NAME,
        constants.MANUAL_VERIFICATION_STAGE_NAME,
        config['gocd_username'],
        config['gocd_password'],
        'https://{}'.format(config['gocd_url']),
        config['hipchat_token']
    )

    # For now, only trigger this pipeline manually. Later, it'll trigger on a cron.
    stage.set_has_manual_approval()

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
    cut_rc = edxapp_group.ensure_replacement_of_pipeline(constants.PRERELEASE_EDXAPP_CUT_RC_PIPELINE_NAME)
    cut_rc.set_label_template('${edx-platform[:7]}-${COUNT}')

    cut_rc_stage = cut_rc.ensure_stage(constants.CUT_PRIVATE_RC_STAGE_NAME)
    cut_rc_job = cut_rc_stage.ensure_job(constants.CUT_PRIVATE_RC_JOB_NAME)
    tasks.generate_package_install(cut_rc_job, 'tubular')
    private_releases.generate_create_private_release_candidate(
        cut_rc_job, config['git_token'],
        ('edx', 'edx-platform'),
        'master',
        EDX_PLATFORM().branch,
        ('edx', 'edx-platform-private'),
        'security-release',
        EDX_PLATFORM_PRIVATE().branch,
        target_reference_repo='edx-platform-private',
    )
    # Delay completing this job to give GoCD time to figure out that the edx-platform-private
    # material is updated, so that it doesn't trigger the downstream pipeline without that
    # changed material.
    cut_rc_job.add_task(tasks.bash_task("sleep 60s"))

    cut_rc_material = PipelineMaterial(
        cut_rc.name,
        constants.CUT_PRIVATE_RC_STAGE_NAME,
        material_name='cut_private_rc'
    )

    pipeline = edxapp_group.ensure_replacement_of_pipeline("prerelease_edxapp_materials_latest")
    pipeline.set_label_template('${{{}}}'.format(cut_rc_material._PipelineMaterial__material_name))  # pylint: disable=no-member, protected-access

    for material in (
            CONFIGURATION, EDX_SECURE, EDGE_SECURE,
            EDX_MICROSITE, EDX_INTERNAL, EDGE_INTERNAL,
    ):
        cut_rc.ensure_material(material(ignore_patterns=[]))
        pipeline.ensure_material(material())

    cut_rc.ensure_material(TUBULAR())
    cut_rc.ensure_material(EDX_PLATFORM(material_name='edx-platform', ignore_patterns=[]))

    pipeline.ensure_material(TUBULAR())
    pipeline.ensure_material(EDX_PLATFORM())
    pipeline.ensure_material(EDX_PLATFORM_PRIVATE(ignore_patterns=[]))
    pipeline.ensure_material(cut_rc_material)

    stage = pipeline.ensure_stage(constants.PRERELEASE_MATERIALS_STAGE_NAME)
    job = stage.ensure_job(constants.PRERELEASE_MATERIALS_JOB_NAME)
    tasks.generate_package_install(job, 'tubular')

    private_rc_artifact = utils.ArtifactLocation(
        cut_rc.name,
        cut_rc_stage.name,
        cut_rc_job.name,
        constants.PRIVATE_RC_FILENAME
    )

    private_releases.generate_private_rc_assertion(job, private_rc_artifact)

    # This prevents the commit being released from being lost when the new
    # release-candidate is cut. However, this will require a janitor job to
    # deal with any releases that are never completed.
    tasks.generate_create_branch(
        pipeline, job, config['git_token'], 'edx', 'edx-platform',
        target_branch="release-candidate-$GO_PIPELINE_COUNTER",
        sha='$GO_REVISION_EDX_PLATFORM')
    tasks.generate_create_branch(
        pipeline, job, config['git_token'], 'edx', 'edx-platform-private',
        target_branch="release-candidate-$GO_PIPELINE_COUNTER",
        sha='$GO_REVISION_EDX_PLATFORM_PRIVATE')

    return pipeline


def launch_and_terminate_subset_pipeline(
        pipeline_group,
        stage_builders,
        config,
        edp,
        pipeline_name,
        ami_artifact=None,
        auto_run=False,
        post_cleanup_builders=None,
        pre_launch_builders=None,
):
    """
    Arguments:
        pipeline_group (gomatic.PipelineGroup): The group in which to create this pipeline
        stage_builders (list): a list of methods that will create pipeline stages used
            between instance launch and cleanup
        ami_artifact (ArtifactLocation): The ami to use to launch the
            instances on. If None, select that ami based on the supplied ``edp``.
        edp (EDP): The environment-deployment-play that identifies the AMI
        config (dict): the configuration dictionary
        pipeline_name (str): name of the pipeline
        auto_run (bool): Should this pipeline auto execute?
        post_cleanup_builders (list): a list of methods that will create pipeline stages used
            after the cleanup has run
        pre_launch_builders (list): a list of methods that will create pipeline stages used
            before instance launch

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
            edp,
            base_ami_id
        )
        ami_artifact = utils.ArtifactLocation(
            pipeline.name,
            constants.BASE_AMI_SELECTION_STAGE_NAME,
            constants.BASE_AMI_SELECTION_JOB_NAME,
            constants.BASE_AMI_OVERRIDE_FILENAME,
        )

    if pre_launch_builders:
        for builder in pre_launch_builders:
            builder(pipeline, config)

    launch_stage = stages.generate_launch_instance(
        pipeline,
        config['aws_access_key_id'],
        config['aws_secret_access_key'],
        config['ec2_vpc_subnet_id'],
        config['ec2_security_group_id'],
        config['ec2_instance_profile_name'],
        base_ami_id,
        base_ami_id_artifact=ami_artifact,
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


def generate_build_stages(app_repo, edp, theme_url, configuration_secure_repo,
                          configuration_internal_repo, configuration_url):
    """
    Generate the stages needed to build an edxapp AMI.
    """
    def builder(pipeline, config):
        """
        A builder for the stages needed to build an edxapp AMI.
        """
        stages.generate_run_play(
            pipeline,
            'playbooks/edx-east/edxapp.yml',
            edp=edp,
            private_github_key=config['github_private_key'],
            app_repo=app_repo,
            configuration_secure_dir='{}-secure'.format(edp.deployment),
            configuration_internal_dir='{}-internal'.format(edp.deployment),
            hipchat_token=config['hipchat_token'],
            hipchat_room='release',
            edx_platform_version='$GO_REVISION_EDX_PLATFORM',
            edx_platform_repo='$APP_REPO',
            configuration_version='$GO_REVISION_CONFIGURATION',
            edxapp_theme_source_repo=theme_url,
            # Currently, edx-theme isn't exposed as a material. See https://openedx.atlassian.net/browse/TE-1874
            # edxapp_theme_version='$GO_REVISION_EDX_THEME',
            # edxapp_theme_name='$EDXAPP_THEME_NAME',
            disable_edx_services='true',
            COMMON_TAG_EC2_INSTANCE='true',
            cache_id='$GO_PIPELINE_COUNTER'
        )

        stages.generate_create_ami_from_instance(
            pipeline,
            edp=edp,
            app_repo=app_repo,
            app_version='$GO_REVISION_EDX_PLATFORM',
            configuration_secure_repo=configuration_secure_repo,
            configuration_internal_repo=configuration_internal_repo,
            configuration_repo=configuration_url,
            hipchat_token=config['hipchat_token'],
            hipchat_room='release pipeline',
            configuration_version='$GO_REVISION_CONFIGURATION',
            configuration_secure_version='$GO_REVISION_{}_SECURE'.format(edp.deployment.upper()),
            configuration_internal_version='$GO_REVISION_{}_SECURE'.format(edp.deployment.upper()),
            aws_access_key_id=config['aws_access_key_id'],
            aws_secret_access_key=config['aws_secret_access_key'],
            edxapp_theme_source_repo=theme_url,
            edxapp_theme_version='$GO_REVISION_EDX_MICROSITE',
        )

        return pipeline
    return builder


def generate_migrate_stages(pipeline, config):
    """
    Generate stages to manage the migration of an environment,
    and add them to ``pipeline``.

    Required Config Values:
        db_migration_pass
        migration_duration_threshold
        db_migration_user
        play_name
        application_path
        alert_from_address
        alert_to_addresses
    """
    #
    # Create the DB migration running stage.
    #
    ansible_inventory_location = utils.ArtifactLocation(
        pipeline.name,
        constants.LAUNCH_INSTANCE_STAGE_NAME,
        constants.LAUNCH_INSTANCE_JOB_NAME,
        constants.ANSIBLE_INVENTORY_FILENAME
    )
    instance_ssh_key_location = utils.ArtifactLocation(
        pipeline.name,
        constants.LAUNCH_INSTANCE_STAGE_NAME,
        constants.LAUNCH_INSTANCE_JOB_NAME,
        constants.KEY_PEM_FILENAME
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

    for sub_app in EDXAPP_SUBAPPS:
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


def generate_deploy_stages(
        pipeline_name_build, prod_build_pipelines, stage_deploy_pipeline,
        auto_deploy_ami=False
):
    """
    Create a builder function that adds deployment stages to a pipeline.
    """
    def builder(pipeline, config):
        """
        Add stages required to deploy edxapp to an environment to the
        supplied pipeline.

        Required Config Parameters:
            asgard_api_endpoints
            asgard_token
            aws_access_key_id
            aws_secret_access_key
            github_token
            edx_environment
        """
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
        stages.generate_deployment_messages(
            pipeline,
            prod_build_pipelines,
            stage_deploy_pipeline,
            'edx',
            'edx-platform',
            '$GITHUB_TOKEN',
            '$GO_REVISION_EDX_PLATFORM',
            constants.ReleaseStatus[config['edx_environment']],
            config['jira_user'],
            config['jira_password'],
            config['github_token'],
            base_ami_artifact=base_ami_file_location,
            ami_tag_app='edx_platform',
        )
        return pipeline
    return builder


def generate_cleanup_stages(pipeline, config, launch_stage):
    """
    Create the stage to terminate the EC2 instance used to both build the AMI and run DB migrations.

    Required Config Parameters:
        aws_access_key_id
        aws_secret_access_key
        hipchat_token
    """
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


def manual_verification(edxapp_deploy_group):
    """
    Variables needed for this pipeline:
    materials: A list of dictionaries of the materials used in this pipeline
    upstream_pipelines: a list of dictionaries of the upstream pipelines that feed in to the manual verification
    """
    pipeline = edxapp_deploy_group.ensure_replacement_of_pipeline(EDXAPP_MANUAL_PIPELINE_NAME)

    for material in (
            TUBULAR, CONFIGURATION, EDX_PLATFORM, EDX_PLATFORM_PRIVATE, EDX_SECURE, EDGE_SECURE,
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
    """
    Add stages to run end-to-end tests against edxapp to the specified ``pipeline``.

    Required Config Parameters:
        jenkins_user_token
        jenkins_job_token
        jenkins_user_name
    """
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


def rollback_asgs(
        edxapp_deploy_group, pipeline_name, build_pipeline,
        deploy_pipeline, config,
        prod_build_pipelines, stage_deploy_pipeline,
):
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

    # Message PRs being rolled back
    pipeline.ensure_unencrypted_secure_environment_variables({'GITHUB_TOKEN': config['github_token']})
    stages.generate_deployment_messages(
        pipeline,
        prod_build_pipelines,
        stage_deploy_pipeline,
        'edx',
        'edx-platform',
        '$GITHUB_TOKEN',
        '$GO_REVISION_EDX_PLATFORM',
        constants.ReleaseStatus.ROLLED_BACK,
        config['jira_user'],
        config['jira_password'],
        config['github_token'],
        base_ami_artifact=base_ami_file_location,
        ami_tag_app='edx_platform',
    )

    return pipeline


def armed_stage_builder(pipeline, config):  # pylint: disable=unused-argument
    """
    Add an armed stage to pipeline.
    """
    stages.generate_armed_stage(pipeline, constants.ARM_PRERELEASE_STAGE)
    return pipeline


def rollback_database(build_pipeline, deploy_pipeline):
    """
    Arguments:
        build_pipeline (gomatic.Pipeline): Pipeline source of the launch info (ami-id)
        deploy_pipeline (gomatic.Pipeline): Pipeline source of the migration information

    Configuration Required:
        aws_access_key_id
        aws_secret_access_key
        hipchat_token
        ec2_vpc_subnet_id
        ec2_security_group_id
        ec2_instance_profile_name
        db_migration_user
        db_migration_pass
        play_name`
        application_name
        edxapp_subapps
    """
    def builder(pipeline, config):
        """
        Add database rollback stages to ``pipeline``.
        """
        for material in (
                TUBULAR, CONFIGURATION, EDX_PLATFORM, EDX_PLATFORM_PRIVATE, EDX_SECURE, EDGE_SECURE,
                EDX_MICROSITE, EDX_INTERNAL, EDGE_INTERNAL,
        ):
            pipeline.ensure_material(material())

        ansible_inventory_location = utils.ArtifactLocation(
            pipeline.name,
            constants.LAUNCH_INSTANCE_STAGE_NAME,
            constants.LAUNCH_INSTANCE_JOB_NAME,
            constants.ANSIBLE_INVENTORY_FILENAME
        )
        instance_ssh_key_location = utils.ArtifactLocation(
            pipeline.name,
            constants.LAUNCH_INSTANCE_STAGE_NAME,
            constants.LAUNCH_INSTANCE_JOB_NAME,
            constants.KEY_PEM_FILENAME
        )

        # Specify the upstream deploy pipeline material for this rollback pipeline.
        # Assumes there's only a single upstream pipeline material for this pipeline.
        pipeline.ensure_material(
            PipelineMaterial(
                pipeline_name=deploy_pipeline.name,
                stage_name=constants.DEPLOY_AMI_STAGE_NAME,
                material_name='deploy_pipeline',
            )
        )

        # We need the build_pipeline upstream so that we can fetch the AMI selection artifact from it
        pipeline.ensure_material(
            PipelineMaterial(
                pipeline_name=build_pipeline.name,
                stage_name=constants.BUILD_AMI_STAGE_NAME,
                material_name='select_base_ami',
            )
        )
        # Create a a stage for migration rollback.
        for sub_app in EDXAPP_SUBAPPS:
            migration_artifact = utils.ArtifactLocation(
                deploy_pipeline.name,
                constants.APPLY_MIGRATIONS_STAGE + "_" + sub_app,
                constants.APPLY_MIGRATIONS_JOB,
                constants.MIGRATION_OUTPUT_DIR_NAME,
                is_dir=True
            )

            stages.generate_rollback_migrations(
                pipeline,
                db_migration_pass=config['db_migration_pass'],
                inventory_location=ansible_inventory_location,
                instance_key_location=instance_ssh_key_location,
                migration_info_location=migration_artifact,
                application_user=config['db_migration_user'],
                application_name=config['play_name'],
                application_path=config['application_path'],
                sub_application_name=sub_app
            )
        return pipeline
    return builder


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
            TUBULAR, CONFIGURATION, EDX_PLATFORM, EDX_PLATFORM_PRIVATE, EDX_SECURE, EDGE_SECURE,
            EDX_MICROSITE, EDX_INTERNAL, EDGE_INTERNAL
    ):
        pipeline.ensure_material(material())

    # Create a single stage in the pipeline which will:
    #   - merge the RC branch into the release branch
    #   - tag the release branch

    git_stage = pipeline.ensure_stage(constants.GIT_MERGE_RC_BRANCH_STAGE_NAME)

    jobs.generate_merge_release_candidate(
        pipeline,
        git_stage,
        token=config['github_token'],
        org='edx',
        repo='edx-platform',
        target_branch='release',
        head_sha='$GO_REVISION_EDX_PLATFORM',
        fast_forward_only=True,
        reference_repo='edx-platform',
    )
    jobs.generate_tag_commit(
        git_stage,
        'edx-platform',
        deploy_artifact=deploy_artifact,
        org='edx',
        repo='edx-platform',
        head_sha='$GO_REVISION_EDX_PLATFORM',
    )
    jobs.generate_tag_commit(
        git_stage,
        'edx-platform-private',
        deploy_artifact=deploy_artifact,
        org='edx',
        repo='edx-platform-private',
        head_sha='$GO_REVISION_EDX_PLATFORM_PRIVATE',
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
