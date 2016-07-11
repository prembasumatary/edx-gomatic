from gomatic import *
import edxpipelines.patterns.tasks as tasks


# Names for the standard stages/jobs
DEPLOY_AMI_STAGE_NAME = 'Deploy-AMI'
DEPLOY_AMI_JOB_NAME = 'Deploy_AMI_Job'
RUN_MIGRATIONS_STAGE_NAME = 'Apply-Migrations'
RUN_MIGRATIONS_JOB_NAME = 'Apply_Migrations_Job'
BUILD_AMI_STAGE_NAME = 'Build-AMI'
BUILD_AMI_JOB_NAME = 'Build_AMI_Job'
TERMINATE_INSTANCE_STAGE_NAME = 'Cleanup-AMI-Instance'
TERMINATE_INSTANCE_JOB_NAME = 'Cleanup_AMI_Instance_Job'
LAUNCH_INSTANCE_STAGE_NAME = 'launch_instance'
LAUNCH_INSTANCE_JOB_NAME = 'launch_instance_job'
RUN_PLAY_STAGE_NAME = "run_play"
RUN_PLAY_JOB_NAME = "run_play_job"
ARTIFACT_PATH = 'target'


def generate_asg_cleanup(pipeline,
                         asgard_api_endpoints,
                         asgard_token,
                         aws_access_key_id,
                         aws_secret_access_key,
                         manual_approval=False):
    """
    Generates stage which calls the ASG cleanup script.

    Args:
        pipeline (gomatic.Pipeline):
        asgard_api_endpoints (str): canonical URL for asgard.
        asgard_token (str): Asgard token to use for authentication
        aws_access_key_id (str): AWS key ID for auth
        aws_secret_access_key (str): AWS secret key for auth
        manual_approval (bool): Should this stage require manual approval?

    Returns:
        gomatic.Stage
    """
    pipeline.ensure_environment_variables({'ASGARD_API_ENDPOINTS': asgard_api_endpoints}) \
            .ensure_encrypted_environment_variables({'ASGARD_API_TOKEN': asgard_token,
                                                     'AWS_ACCESS_KEY_ID': aws_access_key_id,
                                                     'AWS_SECRET_ACCESS_KEY': aws_secret_access_key})

    stage = pipeline.ensure_stage("ASG-Cleanup-Stage")
    if manual_approval:
        stage.set_has_manual_approval()
    job = stage.ensure_job("Cleanup-ASGS")
    tasks.generate_requirements_install(job, 'tubular')
    job.add_task(ExecTask(['/usr/bin/python', 'scripts/cleanup-asgs.py'], working_dir="tubular"))

    return stage


def generate_launch_instance(pipeline,
                             aws_access_key_id,
                             aws_secret_access_key,
                             ec2_vpc_subnet_id,
                             ec2_security_group_id,
                             ec2_instance_profile_name,
                             base_ami_id,
                             manual_approval=False):
    """
    Pattern to launch an AMI. Generates 3 artifacts:
        key.pem             - Private key material generated for this instance launch
        launch_info.yml     - yaml file that contains information about the instance launched
        ansible_inventory   - a list of private aws IP addresses that can be fed in to ansible to run playbooks

    Args:
        pipeline (gomatic.Pipeline):
        aws_access_key_id (str): AWS key ID for auth
        aws_secret_access_key (str): AWS secret key for auth
        ec2_vpc_subnet_id (str):
        ec2_security_group_id (str):
        ec2_instance_profile_name (str):
        base_ami_id (str): the ami-id used to launch the instance
        manual_approval (bool): Should this stage require manual approval?

    Returns:
        gomatic.Stage

    """
    pipeline.ensure_encrypted_environment_variables({'AWS_ACCESS_KEY_ID': aws_access_key_id,
                                                     'AWS_SECRET_ACCESS_KEY': aws_secret_access_key})
    pipeline.ensure_environment_variables({'EC2_VPC_SUBNET_ID': ec2_vpc_subnet_id,
                                           'EC2_SECURITY_GROUP_ID': ec2_security_group_id,
                                           'EC2_ASSIGN_PUBLIC_IP': 'no',
                                           'EC2_TIMEOUT': '300',
                                           'EC2_REGION': 'us-east-1',
                                           'EBS_VOLUME_SIZE': '50',
                                           'EC2_INSTANCE_TYPE': 't2.large',
                                           'EC2_INSTANCE_PROFILE_NAME': ec2_instance_profile_name,
                                           'NO_REBOOT': 'no',
                                           'BASE_AMI_ID': base_ami_id,
                                           })

    stage = pipeline.ensure_stage(LAUNCH_INSTANCE_STAGE_NAME)
    if manual_approval:
        stage.set_has_manual_approval()

    job = stage.ensure_job(LAUNCH_INSTANCE_JOB_NAME)
    # Install the requirements.
    tasks.generate_requirements_install(job, 'tubular')
    tasks.generate_requirements_install(job, 'configuration')

    tasks.generate_launch_instance(job)

    return stage


def generate_run_play(pipeline,
                      playbook_path,
                      play,
                      deployment,
                      edx_environment,
                      app_repo,
                      configuration_secure_repo,
                      private_github_key='',
                      configuration_repo='https://github.com/edx/configuration.git',
                      app_version='master',
                      configuration_version='master',
                      configuration_secure_version='master',
                      hipchat_auth_token='',
                      hipchat_room='',
                      manual_approval=False):
    """
    Pattern assumes that generate_launch_instance stage was used launch the instance preceding this stage.
    Requires the ansible_inventory and key.pem files to be in the target/ directory

    Args:
        pipeline (gomatic.Pipeline):
        manual_approval (bool): does this stage require manual approval?

    Returns:

    """
    # setup the necessary environment variables
    pipeline.ensure_encrypted_environment_variables({'HIPCHAT_AUTH_TOKEN': hipchat_auth_token,
                                                     'PRIVATE_GITHUB_KEY': private_github_key})
    pipeline.ensure_environment_variables({'PLAY': play,
                                           'DEPLOYMENT': deployment,
                                           'EDX_ENVIRONMENT': edx_environment,
                                           'APP_REPO': app_repo,
                                           'APP_VERSION': app_version,
                                           'CONFIGURATION_REPO': configuration_repo,
                                           'CONFIGURATION_VERSION': configuration_version,
                                           'CONFIGURATION_SECURE_REPO': configuration_secure_repo,
                                           'CONFIGURATION_SECURE_VERSION': configuration_secure_version,
                                           'ARTIFACT_PATH': 'target/',
                                           'HIPCHAT_ROOM': hipchat_room})


    stage = pipeline.ensure_stage(RUN_PLAY_STAGE_NAME)
    if manual_approval:
        stage.set_has_manual_approval()
    job = stage.ensure_job(RUN_PLAY_JOB_NAME)

    # Install the requirements.
    tasks.generate_requirements_install(job, 'tubular')
    tasks.generate_requirements_install(job, 'configuration')
    tasks.generate_target_directory(job)

    # fetch the key material
    artifact_params = {
        "pipeline": pipeline.name,
        "stage": LAUNCH_INSTANCE_STAGE_NAME,
        "job": LAUNCH_INSTANCE_JOB_NAME,
        "src": FetchArtifactFile("key.pem"),
        "dest": "target"
    }
    job.add_task(FetchArtifactTask(**artifact_params))

    # fetch the launch_info.yml
    artifact_params = {
        "pipeline": pipeline.name,
        "stage": LAUNCH_INSTANCE_STAGE_NAME,
        "job": LAUNCH_INSTANCE_JOB_NAME,
        "src": FetchArtifactFile("launch_info.yml"),
        "dest": "target"
    }
    job.add_task(FetchArtifactTask(**artifact_params))

    # fetch the inventory file
    artifact_params = {
        "pipeline": pipeline.name,
        "stage": LAUNCH_INSTANCE_STAGE_NAME,
        "job": LAUNCH_INSTANCE_JOB_NAME,
        "src": FetchArtifactFile("ansible_inventory"),
        "dest": "target"
    }
    job.add_task(FetchArtifactTask(**artifact_params))

    # Setup secure configuration for any needed secrets.
    secure_dir = 'secure_repo'
    tasks.fetch_secure_configuration(job, secure_dir)

    # Check out the requested version of configuration.
    # Required if a particular SHA hash is needed.
    tasks.guarantee_configuration_version(job)

    tasks.generate_run_app_playbook(job, secure_dir, playbook_path)


def generate_create_ami_from_instance(pipeline,
                                      play,
                                      deployment,
                                      edx_environment,
                                      app_repo,
                                      configuration_secure_repo,
                                      aws_access_key_id,
                                      aws_secret_access_key,
                                      configuration_repo='https://github.com/edx/configuration.git',
                                      app_version='master',
                                      configuration_version='master',
                                      configuration_secure_version='master',
                                      ami_creation_timeout="3600",
                                      ami_wait='yes',
                                      cache_id='',
                                      artifact_path='target',
                                      hipchat_room='release',
                                      manual_approval=False,
                                      **kwargs):
    """
    Generates an artifact ami.yml:
        ami_id: ami-abcdefg
        ami_message: AMI creation operation complete
        ami_state: available

    Args:
        pipeline:
        play:
        deployment:
        edx_environment:
        app_repo:
        configuration_secure_repo:
        configuration_repo:
        app_version:
        configuration_version:
        configuration_secure_version:
        ami_creation_timeout:
        ami_wait:
        cache_id:
        artifact_path:
        hipchat_room:
        manual_approval:
        **kwargs:

    Returns:
        gomatic.Stage

    """
    stage = pipeline.ensure_stage(BUILD_AMI_STAGE_NAME)
    if manual_approval:
        stage.set_has_manual_approval()
    pipeline.ensure_encrypted_environment_variables({'AWS_ACCESS_KEY_ID': aws_access_key_id,
                                                     'AWS_SECRET_ACCESS_KEY': aws_secret_access_key})
    variables = {'PLAY': play,
                 'DEPLOYMENT': deployment,
                 'EDX_ENVIRONMENT': edx_environment,
                 'APP_REPO': app_repo,
                 'APP_VERSION': app_version,
                 'CONFIGURATION_REPO': configuration_repo,
                 'CONFIGURATION_VERSION': configuration_version,
                 'CONFIGURATION_SECURE_REPO': configuration_secure_repo,
                 'CONFIGURATION_SECURE_VERSION': configuration_secure_version,
                 'AMI_CREATION_TIMEOUT': ami_creation_timeout,
                 'AMI_WAIT': ami_wait,
                 'CACHE_ID': cache_id,  # gocd build number
                 'ARTIFACT_PATH': artifact_path,
                 'HIPCHAT_ROOM': hipchat_room,
                 }
    # variables.update(kwargs)
    pipeline.ensure_environment_variables(variables)

    job = stage.ensure_job(BUILD_AMI_JOB_NAME)

    # Install the requirements.
    tasks.generate_requirements_install(job, 'tubular')
    tasks.generate_requirements_install(job, 'configuration')

    tasks.generate_target_directory(job)

    # fetch the key material
    artifact_params = {
        "pipeline": pipeline.name,
        "stage": LAUNCH_INSTANCE_STAGE_NAME,
        "job": LAUNCH_INSTANCE_JOB_NAME,
        "src": FetchArtifactFile("launch_info.yml"),
        "dest": 'target'
    }
    job.add_task(FetchArtifactTask(**artifact_params))

    # Create an AMI from the instance
    tasks.generate_create_ami(job)

    return stage


def generate_build_ami_single_stage(pipeline,
                                    playbook_path,
                                    manual_approval=False):
    """
    Generates a stage which builds an AMI after running a particular playbook against the instance.

    Args:
        pipeline (gomatic.Pipeline):
        playbook_path (str): path to the configuration playbook, relative to the top-level configuration dir, ex. 'playbooks/edx-east/programs.yml'
        manual_approval (bool): does this stage require manual approval?

    Returns:
        gomatic.Stage
    """
    stage = pipeline.ensure_stage(BUILD_AMI_STAGE_NAME)
    if manual_approval:
        stage.set_has_manual_approval()
    job = stage.ensure_job(BUILD_AMI_JOB_NAME)\
               .ensure_artifacts(set([BuildArtifact('configuration'),
                                      BuildArtifact('target/config_secure_sha'),
                                      BuildArtifact('tubular')]))

    # Install the requirements.
    tasks.generate_requirements_install(job, 'tubular')
    tasks.generate_requirements_install(job, 'configuration')

    # Setup secure configuration for any needed secrets.
    secure_dir = 'secure_repo'
    tasks.fetch_secure_configuration(job, secure_dir)

    # Check out the requested version of configuration.
    # Required if a particular SHA hash is needed.
    tasks.guarantee_configuration_version(job)

    # Launch EC2 instance
    tasks.generate_launch_instance(job)

    # Run the programs playbook on the EC2 instance.
    tasks.generate_run_app_playbook(job, secure_dir, playbook_path)

    # Create an AMI from the instance
    tasks.generate_create_ami(job)

    # Cleanup EC2 instance if launching the instance failed.
    tasks.generate_ami_cleanup(job, runif='failed')

    return stage


def generate_basic_deploy_ami(pipeline,
                              asgard_api_endpoints,
                              asgard_token,
                              aws_access_key_id,
                              aws_secret_access_key,
                              ami_file_location,
                              manual_approval=False):
    """
    Generates a stage which deploys an AMI via Asgard.

    Args:
        pipeline (gomatic.Pipeline):
        asgard_api_endpoints (str): canonical URL for asgard.
        asgard_token (str):
        aws_access_key_id (str):
        aws_secret_access_key (str):
        ami_file_location (ArtifactLocation): The location of yaml artifact that has the `ami_id`, so that we can fetch it.
        manual_approval (bool): Should this stage require manual approval?
    Returns:
        gomatic.Stage
    """
    pipeline.ensure_environment_variables(
        {
            'ASGARD_API_ENDPOINTS': asgard_api_endpoints
        }
    ).ensure_encrypted_environment_variables(
        {
            'ASGARD_API_TOKEN': asgard_token,
            'AWS_ACCESS_KEY_ID': aws_access_key_id,
            'AWS_SECRET_ACCESS_KEY': aws_secret_access_key,
        }
    )

    stage = pipeline.ensure_stage(DEPLOY_AMI_STAGE_NAME)
    if manual_approval:
        stage.set_has_manual_approval()
    job = stage.ensure_job(DEPLOY_AMI_JOB_NAME)
    tasks.generate_requirements_install(job, 'tubular')

    artifact_params = {
        "pipeline": ami_file_location.pipeline,
        "stage": ami_file_location.stage,
        "job": ami_file_location.job,
        "src": FetchArtifactFile(ami_file_location.file_name),
        "dest": 'tubular'
    }
    job.add_task(FetchArtifactTask(**artifact_params))
    job.add_task(ExecTask(
        [
            '/usr/bin/python',
            'scripts/asgard-deploy.py',
            '--config-file', ami_file_location.file_name,
        ],
        working_dir="tubular"))
    return stage


def generate_edp_validation(pipeline,
                            hipchat_auth_token,
                            hipchat_channels,
                            asgard_api_endpoints,
                            ami_deployment,
                            ami_environment,
                            ami_play,
                            manual_approval=False):
    """
    Generate stage which checks an AMI's environment/deployment/play (EDP) against the allowed EDP.
    Stage fails if the EDPs don't match.

    Args:
        pipeline (gomatic.Pipeline):
        hipchat_auth_token (str):
        hipchat_channels (str): The channels/users to notify
        asgard_api_endpoints (str): canonical URL for asgard.
        ami_deployment (str): typically one of: [edx, edge, etc...]
        ami_environment (str): typically one of: [stage, prod, loadtest, etc...]
        ami_play (str):
        manual_approval (bool): Should this stage require manual approval?

    Returns:
        gomatic.Stage
    """
    pipeline.ensure_environment_variables({'AMI_ID': None,
                                           'AMI_DEPLOYMENT': ami_deployment,
                                           'HIPCHAT_CHANNELS': hipchat_channels,
                                           'ASGARD_API_ENDPOINTS': asgard_api_endpoints,
                                           'AMI_ENVIRONMENT': ami_environment,
                                           'AMI_PLAY': ami_play})\
            .ensure_encrypted_environment_variables({'HIPCHAT_AUTH_TOKEN': hipchat_auth_token})

    stage = pipeline.ensure_stage("Validation")
    if manual_approval:
        stage.set_has_manual_approval()
    job = stage.ensure_job("EDPValidation")
    tasks.generate_requirements_install(job, 'tubular')
    job.add_task(
        ExecTask(
            [
                '/usr/bin/python',
                'scripts/validate_edp.py'
            ],
            working_dir='tubular'
        )
    )
    job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                '/usr/bin/python '
                'scripts/submit_hipchat_msg.py '
                '-m '
                '"${AMI_ID} is not tagged for ${AMI_ENVIRONMENT}-${AMI_DEPLOYMENT}-${AMI_PLAY}. '
                'Are you sure you\'re deploying the right AMI to the right app?" '
                '--color "red"'
            ],
            working_dir='tubular',
            runif='failed'
        )
    )

    return stage


def generate_run_migrations(pipeline,
                            db_migration_pass,
                            artifact_path,
                            inventory_location,
                            instance_key_location,
                            manual_approval=False):
    """
    Generate the stage that applies/runs migrations.

    Args:
        pipeline (gomatic.Pipeline): Pipeline to which to add the run migrations stage.
        db_migration_pass (str): Password for the DB user used to run migrations.
        artifact_path (str): Path where the artifacts can be found.
        inventory_location (ArtifactLocation): Location of inventory containing the IP address of the EC2 instance, for fetching.
        instance_key_location (ArtifactLocation): Location of SSH key used to access the EC2 instance, for fetching.
        manual_approval (bool): Should this stage require manual approval?

    Returns:
        gomatic.Stage
    """
    pipeline.ensure_environment_variables(
        {
            'APPLICATION_USER': 'programs',
            'APPLICATION_NAME': 'programs',
            'APPLICATION_PATH': '/edx/app/programs',
            'DB_MIGRATION_USER': 'migrate',
            'ARTIFACT_PATH': artifact_path,
        }
    )
    pipeline.ensure_encrypted_environment_variables(
        {
            'DB_MIGRATION_PASS': db_migration_pass,
        }
    )

    stage = pipeline.ensure_stage('Apply-Migrations')
    if manual_approval:
        stage.set_has_manual_approval()
    job = stage.ensure_job('Apply_Migrations_Job')

    # Check out the requested version of configuration
    tasks.guarantee_configuration_version(job)

    # Fetch the Ansible inventory to use in reaching the EC2 instance.
    artifact_params = {
        "pipeline": inventory_location.pipeline,
        "stage": inventory_location.stage,
        "job": inventory_location.job,
        "src": FetchArtifactFile(inventory_location.file_name),
        "dest": 'configuration'
    }
    job.add_task(FetchArtifactTask(**artifact_params))

    # Fetch the SSH key to use in reaching the EC2 instance.
    artifact_params = {
        "pipeline": instance_key_location.pipeline,
        "stage": instance_key_location.stage,
        "job": instance_key_location.job,
        "src": FetchArtifactFile(instance_key_location.file_name),
        "dest": 'configuration'
    }
    job.add_task(FetchArtifactTask(**artifact_params))

    # ensure the target directoy exists
    tasks.generate_target_directory(job)

    # fetch the launch_info.yml
    artifact_params = {
        "pipeline": inventory_location.pipeline,
        "stage": inventory_location.stage,
        "job": inventory_location.job,
        "src": FetchArtifactFile("launch_info.yml"),
        "dest": "target"
    }
    job.add_task(FetchArtifactTask(**artifact_params))

    # The SSH key used to access the EC2 instance needs specific permissions.
    job.add_task(
        ExecTask(
            ['/bin/bash', '-c', 'chmod 600 {}'.format(instance_key_location.file_name)],
            working_dir='configuration'
        )
    )

    tasks.generate_requirements_install(job, 'configuration')
    tasks.generate_run_migrations(job)

    # Cleanup EC2 instance if running the migrations failed.
    # I think this should be left for the terminate instance stage
    # tasks.generate_ami_cleanup(job, runif='failed')

    return stage


def generate_terminate_instance(pipeline,
                                instance_info_location,
                                aws_access_key_id,
                                aws_secret_access_key,
                                hipchat_auth_token,
                                ec2_region='us-east-1',
                                artifact_path='target',
                                runif='any',
                                manual_approval=False):
    """
    Generate the stage that terminates an EC2 instance.

    Args:
        pipeline (gomatic.Pipeline): Pipeline to which to add the run migrations stage.
        instance_info_location (ArtifactLocation): Location of YAML file containing instance info from the AMI-building stage, for fetching.
        runif (str): one of ['passed', 'failed', 'any'] Default: any - controls when the stage's terminate task is triggered in the pipeline
        manual_approval (bool): Should this stage require manual approval?

    Returns:
        gomatic.Stage

    """
    pipeline.ensure_encrypted_environment_variables({'AWS_ACCESS_KEY_ID': aws_access_key_id,
                                                     'AWS_SECRET_ACCESS_KEY': aws_secret_access_key,
                                                     'HIPCHAT_TOKEN': hipchat_auth_token})
    pipeline.ensure_environment_variables({'ARTIFACT_PATH': artifact_path,
                                           'EC2_REGION': ec2_region,
                                           'HIPCHAT_ROOM': 'release pipeline'})


    stage = pipeline.ensure_stage(TERMINATE_INSTANCE_STAGE_NAME)
    if manual_approval:
        stage.set_has_manual_approval()
    job = stage.ensure_job(TERMINATE_INSTANCE_JOB_NAME)

    # Fetch the instance info to use in reaching the EC2 instance.
    artifact_params = {
        "pipeline": instance_info_location.pipeline,
        "stage": instance_info_location.stage,
        "job": instance_info_location.job,
        "src": FetchArtifactFile(instance_info_location.file_name),
        "dest": 'target'
    }
    job.add_task(FetchArtifactTask(**artifact_params))

    tasks.generate_ami_cleanup(job, runif=runif)

    return stage
