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


def generate_asg_cleanup(pipeline,
                         asgard_api_endpoints,
                         asgard_token,
                         aws_access_key_id,
                         aws_secret_access_key):
    """
    Generates stage which calls the ASG cleanup script.

    Args:
        pipeline (gomatic.Pipeline):
        asgard_api_endpoints (str): canonical URL for asgard.
        asgard_token (str): Asgard token to use for authentication
        aws_access_key_id (str): AWS key ID for auth
        aws_secret_access_key (str): AWS secret key for auth
    Returns:
        gomatic.Stage
    """
    pipeline.ensure_environment_variables({'ASGARD_API_ENDPOINTS': asgard_api_endpoints}) \
            .ensure_encrypted_environment_variables({'ASGARD_API_TOKEN': asgard_token,
                                                     'AWS_ACCESS_KEY_ID': aws_access_key_id,
                                                     'AWS_SECRET_ACCESS_KEY': aws_secret_access_key})

    stage = pipeline.ensure_stage("ASG-Cleanup-Stage")
    job = stage.ensure_job("Cleanup-ASGS")
    tasks.generate_requirements_install(job, 'tubular')
    job.add_task(ExecTask(['/usr/bin/python', 'scripts/cleanup-asgs.py'], working_dir="tubular"))

    return stage


def generate_build_ami(pipeline, playbook_path):
    """
    Generates a stage which builds an AMI after running a particular playbook against the instance.

    Args:
        pipeline (gomatic.Pipeline):
        playbook_path (str): path to the configuration playbook, relative to the top-level configuration dir, ex. 'playbooks/edx-east/programs.yml'
    Returns:
        gomatic.Stage
    """
    stage = pipeline.ensure_stage(BUILD_AMI_STAGE_NAME)
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
                              ami_file_location):
    """
    Generates a stage which deploys an AMI via Asgard.

    Args:
        pipeline (gomatic.Pipeline):
        asgard_api_endpoints (str): canonical URL for asgard.
        asgard_token (str):
        aws_access_key_id (str):
        aws_secret_access_key (str):
        ami_file_location (ArtifactLocation): The location of yaml artifact that has the `ami_id`, so that we can fetch it.
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

    stage = pipeline.ensure_stage(DEPLOY_AMI_STAGE_NAME).set_has_manual_approval()
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
                            ami_play):
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
                            instance_key_location):
    """
    Generate the stage that applies/runs migrations.

    Args:
        pipeline (gomatic.Pipeline): Pipeline to which to add the run migrations stage.
        db_migration_pass (str): Password for the DB user used to run migrations.
        artifact_path (str): Path where the artifacts can be found.
        inventory_location (ArtifactLocation): Location of inventory containing the IP address of the EC2 instance, for fetching.
        instance_key_location (ArtifactLocation): Location of SSH key used to access the EC2 instance, for fetching.

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
    tasks.generate_ami_cleanup(job, runif='failed')

    return stage


def generate_terminate_instance(pipeline,
                                instance_info_location,
                                runif='any'):
    """
    Generate the stage that terminates an EC2 instance.

    Args:
        pipeline (gomatic.Pipeline): Pipeline to which to add the run migrations stage.
        instance_info_location (ArtifactLocation): Location of YAML file containing instance info from the AMI-building stage, for fetching.
        runif (str): one of ['passed', 'failed', 'any'] Default: any - controls when the stage's terminate task is triggered in the pipeline

    Returns:
        gomatic.Stage

    """
    stage = pipeline.ensure_stage(TERMINATE_INSTANCE_STAGE_NAME)
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
