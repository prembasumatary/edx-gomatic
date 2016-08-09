import re
from gomatic import *

import edxpipelines.utils as utils
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
            GitMaterial("https://github.com/edx/tubular.git", polling=False, destination_directory="tubular"))

    stages.generate_single_stage_deploy_ami(
        pipeline,
        asgard_api_endpoints,
        asgard_token,
        aws_access_key_id,
        aws_secret_access_key
    )
    return configurator


def generate_multistage_pipeline(
        environment,
        deployment,
        play,
        pipeline_group,
        playbook_path,
        app_repo,
        version_var_name,
        service_name,
        hipchat_room,
        config,
        save_config_locally,
        dry_run):
    hipchat_auth_token = config['hipchat_token']
    application_path = '/edx/app/' + service_name
    artifact_path = 'target/'
    app_version = config.get('app_version', constants.APP_REPO_BRANCH)

    gcc = GoCdConfigurator(
        HostRestClient(config['gocd_url'], config['gocd_username'], config['gocd_password'], ssl=True))
    pipeline = gcc.ensure_pipeline_group(pipeline_group) \
        .ensure_replacement_of_pipeline('-'.join([environment, deployment, play])) \
        .ensure_material(GitMaterial(config['tubular_url'],
                                     branch=config.get('tubular_version', 'master'),
                                     material_name='tubular',
                                     polling=False,
                                     destination_directory='tubular')) \
        .ensure_material(GitMaterial(config['configuration_url'],
                                     branch=config['configuration_version'],
                                     material_name='configuration',
                                     polling=False,
                                     destination_directory=constants.PUBLIC_CONFIGURATION_DIR)) \
        .ensure_material(GitMaterial(config['app_repo'],
                                     branch=app_version,
                                     material_name=service_name,
                                     polling=True,
                                     destination_directory=service_name)) \
        .ensure_material(GitMaterial(config['configuration_secure_repo'],
                                     branch=config.get('configuration_secure_version', 'master'),
                                     material_name='configuration_secure',
                                     polling=False,
                                     destination_directory=constants.PRIVATE_CONFIGURATION_LOCAL_DIR))

    pipeline.ensure_environment_variables({
        'APPLICATION_USER': service_name,
        'APPLICATION_NAME': service_name,
        'APPLICATION_PATH': application_path,
        'HIPCHAT_ROOM': hipchat_room,
    })

    pipeline.ensure_encrypted_environment_variables({
        'HIPCHAT_TOKEN': hipchat_auth_token,
    })

    #
    # Create the AMI-building stage.
    #
    stages.generate_launch_instance(
        pipeline,
        config['aws_access_key_id'],
        config['aws_secret_access_key'],
        config['ec2_vpc_subnet_id'],
        config['ec2_security_group_id'],
        config['ec2_instance_profile_name'],
        config['base_ami_id'],
        manual_approval=True
    )

    app_version = '$GO_REVISION_' + re.sub('[\W\d]', '_', service_name.strip()).upper()
    kwargs = {
        version_var_name: app_version,
    }

    stages.generate_run_play(
        pipeline,
        playbook_path,
        play,
        deployment,
        environment,
        app_repo=app_repo,
        private_github_key=config['github_private_key'],
        configuration_repo='https://github.com/edx/configuration.git',
        hipchat_auth_token=hipchat_auth_token,
        hipchat_room=hipchat_room,
        disable_edx_services='true',
        COMMON_TAG_EC2_INSTANCE='true',
        **kwargs
    )


    stages.generate_create_ami_from_instance(
        pipeline,
        play=play,
        deployment=deployment,
        edx_environment=environment,
        app_repo=app_repo,
        app_version=app_version,
        configuration_secure_repo=config['configuration_secure_repo'],
        configuration_repo='https://github.com/edx/configuration.git',
        hipchat_auth_token=hipchat_auth_token,
        hipchat_room=hipchat_room,
        aws_access_key_id=config['aws_access_key_id'],
        aws_secret_access_key=config['aws_secret_access_key'],
    )
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
        'launch_info.yml'
    )
    stages.generate_run_migrations(
        pipeline,
        config['db_migration_pass'],
        artifact_path,
        ansible_inventory_location,
        instance_ssh_key_location,
        launch_info_location,
        service_name,
        service_name,
        application_path
    )

    # TODO NOPE!!!
    if service_name == 'discovery':
        stages.generate_refresh_metadata(
            pipeline,
            ansible_inventory_location,
            instance_ssh_key_location,
            launch_info_location,
            service_name,
            service_name,
            application_path,
            hipchat_auth_token=hipchat_auth_token,
            hipchat_room=hipchat_room
        )

        stages.generate_update_index(
            pipeline,
            ansible_inventory_location,
            instance_ssh_key_location,
            launch_info_location,
            service_name,
            service_name,
            application_path,
            hipchat_auth_token=hipchat_auth_token,
            hipchat_room=hipchat_room
        )

    #
    # Create the stage to deploy the AMI.
    #
    ami_file_location = utils.ArtifactLocation(
        pipeline.name,
        constants.BUILD_AMI_STAGE_NAME,
        constants.BUILD_AMI_JOB_NAME,
        'ami.yml'
    )
    stages.generate_basic_deploy_ami(
        pipeline,
        config['asgard_api_endpoints'],
        config['asgard_token'],
        config['aws_access_key_id'],
        config['aws_secret_access_key'],
        ami_file_location,
        True
    )
    #
    # Create the stage to terminate the EC2 instance used to both build the AMI and run DB migrations.
    #
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
        hipchat_auth_token=hipchat_auth_token,
        hipchat_room=hipchat_room,
        runif='any'
    )
    gcc.save_updated_config(save_config_locally=save_config_locally, dry_run=dry_run)
