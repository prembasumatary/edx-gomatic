import re

from gomatic import *

from gomatic.gocd.materials import PipelineMaterial
from edxpipelines import utils
from edxpipelines import constants
from edxpipelines.patterns import stages


def generate_deploy_pipeline(configurator,
                             pipeline_name,
                             pipeline_group,
                             asgard_api_endpoints,
                             asgard_token,
                             aws_access_key_id,
                             aws_secret_access_key):
    """

    Args:
        configurator (GoCdConfigurator)
        pipeline_name (str):
        pipeline_group (str):
        asgard_api_endpoints (str): url of the asgard API
        asgard_token (str):
        aws_access_key_id (str):
        aws_secret_access_key (str):

    Returns:
        GoCdConfigurator
    """

    pipeline = configurator \
        .ensure_pipeline_group(pipeline_group) \
        .ensure_replacement_of_pipeline(pipeline_name) \
        .set_git_material(
            GitMaterial(
                "https://github.com/edx/tubular.git",
                polling=True,
                destination_directory="tubular",
                ignore_patterns=constants.MATERIAL_IGNORE_ALL_REGEX
            )
        )

    stages.generate_deploy_ami(pipeline,
                               asgard_api_endpoints,
                               asgard_token,
                               aws_access_key_id,
                               aws_secret_access_key,
                               manual_approval=True)
    return configurator


def generate_basic_multistage_pipeline(
        configurator,
        play,
        pipeline_group,
        playbook_path,
        app_repo,
        service_name,
        hipchat_room,
        config,
        post_migration_stages=(),
        skip_migrations=False,
        **kwargs
):
    """
    This pattern generates a pipeline that is suitable for the majority of edX's independently-deployable applications
    (IDAs).

    The generated pipeline will includes stages that do the following:

        1. Launch a new instance on which we will build an AMI.
        2. Run the Ansible play for the service.
        3. Create an AMI based on the instance.
        4. Run migrations.
        5. Deploy the AMI (after manual intervention)
        6. Destroy the instance on which the AMI was built.

    Notes:
        The instance launched/destroyed is NEVER inserted into the load balancer or serving user requests.
    """
    environment = config['edx_environment']
    deployment = config['edx_deployment']

    application_name = service_name
    application_path = '/edx/app/' + service_name
    application_user = service_name
    hipchat_token = config['hipchat_token']

    pipeline = configurator.ensure_pipeline_group(pipeline_group) \
        .ensure_replacement_of_pipeline('-'.join([environment, deployment, play])) \
        .ensure_material(GitMaterial(config['tubular_url'],
                                     branch=config.get('tubular_version', 'master'),
                                     material_name='tubular',
                                     polling=True,
                                     destination_directory='tubular',
                                     ignore_patterns=constants.MATERIAL_IGNORE_ALL_REGEX)) \
        .ensure_material(GitMaterial(config['configuration_url'],
                                     branch=config.get('configuration_version', 'master'),
                                     material_name='configuration',
                                     polling=True,
                                     destination_directory='configuration',
                                     ignore_patterns=constants.MATERIAL_IGNORE_ALL_REGEX)) \
        .ensure_material(GitMaterial(config['app_repo'],
                                     branch=config.get('app_version', 'master'),
                                     material_name=play,
                                     polling=True,
                                     destination_directory=config['app_destination_directory'])) \
        .ensure_material(GitMaterial(config['configuration_secure_repo'],
                                     branch=config.get('configuration_secure_version', 'master'),
                                     material_name='configuration_secure',
                                     polling=True,
                                     destination_directory=constants.PRIVATE_CONFIGURATION_LOCAL_DIR,
                                     ignore_patterns=constants.MATERIAL_IGNORE_ALL_REGEX)) \
        .ensure_material(GitMaterial(config['configuration_internal_repo'],
                                     branch=config.get('configuration_internal_version', 'master'),
                                     material_name='configuration_internal',
                                     polling=True,
                                     destination_directory=constants.INTERNAL_CONFIGURATION_LOCAL_DIR,
                                     ignore_patterns=constants.MATERIAL_IGNORE_ALL_REGEX)) \
        .ensure_environment_variables({
            'APPLICATION_USER': application_user,
            'APPLICATION_NAME': application_name,
            'APPLICATION_PATH': application_path,
        })

    ami_selection_stage = stages.generate_base_ami_selection(
        pipeline,
        config['aws_access_key_id'],
        config['aws_secret_access_key'],
        play,
        deployment,
        environment,
        manual_approval=not config.get('auto_run', False),
    )

    # The artifact that provides the AMI-ID to launch
    ami_artifact = utils.ArtifactLocation(
        pipeline.name,
        ami_selection_stage.name,
        constants.BASE_AMI_SELECTION_JOB_NAME,
        constants.BASE_AMI_OVERRIDE_FILENAME,
    )

    # Launch a new instance on which to build the AMI
    stages.generate_launch_instance(pipeline,
                                    config['aws_access_key_id'],
                                    config['aws_secret_access_key'],
                                    config['ec2_vpc_subnet_id'],
                                    config['ec2_security_group_id'],
                                    config['ec2_instance_profile_name'],
                                    config['base_ami_id'],
                                    upstream_build_artifact=ami_artifact
                                    )

    # Run the Ansible play for the service
    stages.generate_run_play(pipeline,
                             playbook_with_path=playbook_path,
                             play=play,
                             deployment=deployment,
                             edx_environment=environment,
                             app_repo=app_repo,
                             configuration_secure_repo=config['configuration_secure_repo'],
                             configuration_secure_dir=constants.PRIVATE_CONFIGURATION_LOCAL_DIR,
                             # remove above line and uncomment the below once materials are changed over to list.
                             # configuration_secure_dir='{}-secure'.format(config['edx_deployment']),
                             private_github_key=config['github_private_key'],
                             hipchat_token=hipchat_token,
                             hipchat_room=hipchat_room,
                             disable_edx_services='true',
                             COMMON_TAG_EC2_INSTANCE='true',
                             **kwargs
                             )

    # Create an AMI
    stages.generate_create_ami_from_instance(
        pipeline,
        play=play,
        deployment=deployment,
        edx_environment=environment,
        app_repo=app_repo,
        configuration_secure_repo=config['configuration_secure_repo'],
        aws_access_key_id=config['aws_access_key_id'],
        aws_secret_access_key=config['aws_secret_access_key'],
        hipchat_token=hipchat_token,
        hipchat_room=hipchat_room,
        configuration_secure_version='$GO_REVISION_CONFIGURATION_SECURE',
        # remove above line and uncomment the below once materials are changed over to list.
        # configuration_secure_version='$GO_REVISION_{}_SECURE'.format(config['edx_deployment'].upper()),
        **kwargs
    )

    # Run database migrations
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
        'launch_info.yml'
    )

    if not skip_migrations:
        stages.generate_run_migrations(pipeline,
                                       config['db_migration_pass'],
                                       ansible_inventory_location,
                                       instance_ssh_key_location,
                                       launch_info_location,
                                       application_user=application_user,
                                       application_name=application_name,
                                       application_path=application_path
                                       )

    # Run post-migration stages/tasks
    for stage in post_migration_stages:
        stage(
            pipeline,
            ansible_inventory_location,
            instance_ssh_key_location,
            launch_info_location,
            application_user=application_user,
            application_name=application_name,
            application_path=application_path,
            hipchat_token=hipchat_token,
            hipchat_room=hipchat_room
        )

    # Deploy the AMI (after user manually approves)
    ami_file_location = utils.ArtifactLocation(
        pipeline.name,
        constants.BUILD_AMI_STAGE_NAME,
        constants.BUILD_AMI_JOB_NAME,
        'ami.yml'
    )
    stages.generate_deploy_ami(
        pipeline,
        config['asgard_api_endpoints'],
        config['asgard_token'],
        config['aws_access_key_id'],
        config['aws_secret_access_key'],
        ami_file_location,
        manual_approval=not config.get('auto_deploy_ami', False)
    )

    # Terminate the instance used to create the AMI and run migrations. It was never inserted into the
    # load balancer, or serving requests, so this is safe.
    instance_info_location = utils.ArtifactLocation(
        pipeline.name,
        constants.LAUNCH_INSTANCE_STAGE_NAME,
        constants.LAUNCH_INSTANCE_JOB_NAME,
        'launch_info.yml'
    )
    stages.generate_terminate_instance(
        pipeline,
        instance_info_location,
        aws_access_key_id=config['aws_access_key_id'],
        aws_secret_access_key=config['aws_secret_access_key'],
        hipchat_token=hipchat_token,
        runif='any'
    )
