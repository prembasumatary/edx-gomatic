from gomatic import *
from edxpipelines.patterns import stages, jobs
from edxpipelines.utils import ArtifactLocation
import edxpipelines.utils as utils


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

    stages.generate_single_stage_deploy_ami(pipeline,
                                            asgard_api_endpoints,
                                            asgard_token,
                                            aws_access_key_id,
                                            aws_secret_access_key)
    return configurator


def generate_multistage_pipeline(environment,
                                 deployment,
                                 play,
                                 pipeline_group,
                                 playbook_path,
                                 app_repo,
                                 version_var_name,
                                 hipchat_room,
                                 config,
                                 save_config_locally,
                                 dry_run):
    artifact_path = 'target/'
    gcc = GoCdConfigurator(
        HostRestClient(config['gocd_url'], config['gocd_username'], config['gocd_password'], ssl=True))
    pipeline = gcc.ensure_pipeline_group(pipeline_group) \
        .ensure_replacement_of_pipeline('-'.join([environment, deployment, play])) \
        .ensure_material(GitMaterial('https://github.com/edx/tubular',
                                     material_name='tubular',
                                     polling=False,
                                     destination_directory='tubular')) \
        .ensure_material(GitMaterial('https://github.com/edx/configuration',
                                     branch='master',
                                     material_name='configuration',
                                     polling=False,
                                     # NOTE if you want to change this, you should set the
                                     # CONFIGURATION_VERSION environment variable instead
                                     destination_directory='configuration')) \
    #
    # Create the AMI-building stage.
    #
    stages.generate_launch_instance(pipeline,
                                    config['aws_access_key_id'],
                                    config['aws_secret_access_key'],
                                    config['ec2_vpc_subnet_id'],
                                    config['ec2_security_group_id'],
                                    config['ec2_instance_profile_name'],
                                    config['base_ami_id']
                                    )

    kwargs = {
        version_var_name: '$APP_VERSION'
    }
    stages.generate_run_play(pipeline,
                             playbook_path=playbook_path,
                             play=play,
                             deployment=deployment,
                             edx_environment=environment,
                             private_github_key=config['github_private_key'],
                             app_repo=app_repo,
                             configuration_secure_repo=config['configuration_secure_repo'],
                             configuration_repo='https://github.com/edx/configuration.git',
                             hipchat_auth_token=config['hipchat_token'],
                             hipchat_room=hipchat_room,
                             disable_edx_services='true',
                             COMMON_TAG_EC2_INSTANCE='true',
                             **kwargs
                             )
    stages.generate_create_ami_from_instance(pipeline,
                                             play=play,
                                             deployment=deployment,
                                             edx_environment=environment,
                                             app_repo=app_repo,
                                             configuration_secure_repo=config['configuration_secure_repo'],
                                             configuration_repo='https://github.com/edx/configuration.git',
                                             hipchat_auth_token=config['hipchat_token'],
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
    stages.generate_run_migrations(pipeline,
                                   config['db_migration_pass'],
                                   artifact_path,
                                   ansible_inventory_location,
                                   instance_ssh_key_location,
                                   launch_info_location)
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
        hipchat_auth_token=config['hipchat_token'],
        runif='any'
    )
    gcc.save_updated_config(save_config_locally=save_config_locally, dry_run=dry_run)