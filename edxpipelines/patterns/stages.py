from gomatic import *

from edxpipelines import constants
from edxpipelines.patterns import tasks
from edxpipelines.constants import ReleaseStatus
from edxpipelines.utils import ArtifactLocation


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
    pipeline.ensure_environment_variables({'ASGARD_API_ENDPOINTS': asgard_api_endpoints})
    pipeline.ensure_encrypted_environment_variables(
        {
            'ASGARD_API_TOKEN': asgard_token,
            'AWS_ACCESS_KEY_ID': aws_access_key_id,
            'AWS_SECRET_ACCESS_KEY': aws_secret_access_key,
        }
    )

    stage = pipeline.ensure_stage("ASG-Cleanup-Stage")
    if manual_approval:
        stage.set_has_manual_approval()

    job = stage.ensure_job("Cleanup-ASGS")
    tasks.generate_requirements_install(job, 'tubular')
    job.add_task(ExecTask(
        [
            '/usr/bin/python',
            'scripts/cleanup-asgs.py'
        ],
        working_dir="tubular")
    )

    return stage


def generate_base_ami_selection(pipeline,
                                aws_access_key_id,
                                aws_secret_access_key,
                                play=None,
                                deployment=None,
                                edx_environment=None,
                                base_ami_id=None,
                                manual_approval=False
                                ):
    """
    Pattern to find a base AMI for a particular EDP. Generates 1 artifact:
        ami_override.yml    - YAML file that contains information about which base AMI to use in building AMI

    Args:
        pipeline (gomatic.Pipeline):
        aws_access_key_id (str): AWS key ID for auth
        aws_secret_access_key (str): AWS secret key for auth
        play (str): Pipeline's play.
        deployment (str): Pipeline's deployment.
        edx_environment (str): Pipeline's environment.
        base_ami_id (str): the ami-id used to launch the instance, or None to use the provided EDP
        manual_approval (bool): Should this stage require manual approval?

    Returns:
        gomatic.Stage
    """
    pipeline.ensure_encrypted_environment_variables(
        {
            'AWS_ACCESS_KEY_ID': aws_access_key_id,
            'AWS_SECRET_ACCESS_KEY': aws_secret_access_key
        }
    )

    pipeline.ensure_environment_variables(
        {
            'PLAY': play,
            'DEPLOYMENT': deployment,
            'EDX_ENVIRONMENT': edx_environment,
            'BASE_AMI_ID': base_ami_id,
            'BASE_AMI_ID_OVERRIDE': 'yes' if base_ami_id is not None else 'no',
        }
    )

    stage = pipeline.ensure_stage(constants.BASE_AMI_SELECTION_STAGE_NAME)

    if manual_approval:
        stage.set_has_manual_approval()

    # Install the requirements.
    job = stage.ensure_job(constants.BASE_AMI_SELECTION_JOB_NAME)
    tasks.generate_requirements_install(job, 'tubular')

    # Generate an base-AMI-ID-overriding artifact.
    base_ami_override_artifact = '{artifact_path}/{file_name}'.format(
        artifact_path=constants.ARTIFACT_PATH,
        file_name=constants.BASE_AMI_OVERRIDE_FILENAME
    )
    job.ensure_artifacts(set([BuildArtifact(base_ami_override_artifact)]))
    job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                'mkdir -p {artifact_path};'
                'if [[ $BASE_AMI_ID_OVERRIDE != \'yes\' ]];'
                '  then echo "Finding base AMI ID from active ELB/ASG in EDP.";'
                '  /usr/bin/python {ami_script} --environment $EDX_ENVIRONMENT --deployment $DEPLOYMENT --play $PLAY --out_file {override_artifact};'
                'elif [[ -n $BASE_AMI_ID ]];'
                '  then echo "Using specified base AMI ID of \'$BASE_AMI_ID\'";'
                '  /usr/bin/python {ami_script} --override $BASE_AMI_ID --out_file {override_artifact};'
                'else echo "Using environment base AMI ID";'
                '  echo "{empty_dict}" > {override_artifact}; fi;'.format(
                    artifact_path='../' + constants.ARTIFACT_PATH,
                    ami_script='scripts/retrieve_base_ami.py',
                    empty_dict='{}',
                    override_artifact='../' + base_ami_override_artifact
                )
            ],
            working_dir="tubular",
            runif="passed"
        )
    )
    return stage


def generate_launch_instance(pipeline,
                             aws_access_key_id,
                             aws_secret_access_key,
                             ec2_vpc_subnet_id,
                             ec2_security_group_id,
                             ec2_instance_profile_name,
                             base_ami_id,
                             manual_approval=False,
                             ec2_region=constants.EC2_REGION,
                             ec2_instance_type=constants.EC2_INSTANCE_TYPE,
                             ec2_timeout=constants.EC2_LAUNCH_INSTANCE_TIMEOUT,
                             ec2_ebs_volume_size=constants.EC2_EBS_VOLUME_SIZE,
                             upstream_build_artifact=None
                             ):
    """
    Pattern to launch an AMI. Generates 3 artifacts:
        key.pem             - Private key material generated for this instance launch
        launch_info.yml     - yaml file that contains information about the instance launched
        ansible_inventory   - a list of private aws IP addresses that can be fed in to ansible to run playbooks

        Please check here for further information:
        https://github.com/edx/configuration/blob/master/playbooks/continuous_delivery/launch_instance.yml

    Args:
        pipeline (gomatic.Pipeline):
        aws_access_key_id (str): AWS key ID for auth
        aws_secret_access_key (str): AWS secret key for auth
        ec2_vpc_subnet_id (str):
        ec2_security_group_id (str):
        ec2_instance_profile_name (str):
        base_ami_id (str): the ami-id used to launch the instance
        manual_approval (bool): Should this stage require manual approval?
        ec2_region (str):
        ec2_instance_type (str):
        ec2_timeout (str):
        ec2_ebs_volume_size (str):
        upstream_build_artifact (edxpipelines.utils.ArtifactLocation): overrides the base_ami_id and will force
                                                                       the task to run with the AMI built up stream.

    Returns:

    """
    pipeline.ensure_encrypted_environment_variables(
        {
            'AWS_ACCESS_KEY_ID': aws_access_key_id,
            'AWS_SECRET_ACCESS_KEY': aws_secret_access_key
        }
    )

    pipeline.ensure_environment_variables(
        {
            'EC2_VPC_SUBNET_ID': ec2_vpc_subnet_id,
            'EC2_SECURITY_GROUP_ID': ec2_security_group_id,
            'EC2_ASSIGN_PUBLIC_IP': 'no',
            'EC2_TIMEOUT': ec2_timeout,
            'EC2_REGION': ec2_region,
            'EBS_VOLUME_SIZE': ec2_ebs_volume_size,
            'EC2_INSTANCE_TYPE': ec2_instance_type,
            'EC2_INSTANCE_PROFILE_NAME': ec2_instance_profile_name,
            'NO_REBOOT': 'no',
            'BASE_AMI_ID': base_ami_id,
            'ANSIBLE_CONFIG': constants.ANSIBLE_CONTINUOUS_DELIVERY_CONFIG,
        }
    )

    stage = pipeline.ensure_stage(constants.LAUNCH_INSTANCE_STAGE_NAME)

    if manual_approval:
        stage.set_has_manual_approval()

    # Install the requirements.
    job = stage.ensure_job(constants.LAUNCH_INSTANCE_JOB_NAME)
    tasks.generate_requirements_install(job, 'tubular')
    tasks.generate_requirements_install(job, 'configuration')

    # fetch the artifacts if there are any
    artifacts = []
    if upstream_build_artifact:
        job.add_task(
            FetchArtifactTask(
                pipeline=upstream_build_artifact.pipeline,
                stage=upstream_build_artifact.stage,
                job=upstream_build_artifact.job,
                src=FetchArtifactFile(upstream_build_artifact.file_name),
                dest=constants.ARTIFACT_PATH,
            )
        )
        artifacts.append(
            '{artifact_path}/{file_name}'
            .format(
                artifact_path=constants.ARTIFACT_PATH,
                file_name=upstream_build_artifact.file_name
            )
        )

    # Create the instance-launching task.
    tasks.generate_launch_instance(job, artifacts)

    return stage


def generate_run_play(pipeline,
                      playbook_with_path,
                      play,
                      deployment,
                      edx_environment,
                      app_repo,
                      private_github_key='',
                      hipchat_token='',
                      hipchat_room=constants.HIPCHAT_ROOM,
                      manual_approval=False,
                      configuration_secure_dir=constants.PRIVATE_CONFIGURATION_LOCAL_DIR,
                      configuration_internal_dir=constants.INTERNAL_CONFIGURATION_LOCAL_DIR,
                      **kwargs):
    """
    TODO: This currently runs from the configuration/playbooks/continuous_delivery/ directory. Need to figure out how to
    pass in a configuration file to ansible-play correctly. TE-1608

    Assumes:
        - generate_launch_instance stage was used launch the instance preceding this stage.
        - Requires the ansible_inventory and key.pem files to be in the constants.ARTIFACT_DIRECTORY path
        - Play is run from the constants.PUBLIC_CONFIGURATION_DIR
        - Play is run using the constants.ANSIBLE_CONFIG configuration file

    Args:
        pipeline (gomatic.Pipeline):
        playbook_with_path (str):
        play (str):
        deployment (str):
        edx_environment (str):
        app_repo (str) :
        private_github_key (str):
        hipchat_token (str):
        hipchat_room (str):
        manual_approval (bool):
        configuration_secure_dir (str): The secure config directory to use for this play.
        **kwargs (dict):
            k,v pairs:
                k: the name of the option to pass to ansible
                v: the value to use for this option

    Returns:
        gomatic.Stage
    """
    # setup the necessary environment variables
    pipeline.ensure_encrypted_environment_variables(
        {
            'HIPCHAT_TOKEN': hipchat_token,
            'PRIVATE_GITHUB_KEY': private_github_key
        }
    )
    pipeline.ensure_environment_variables(
        {
            'PLAY': play,
            'DEPLOYMENT': deployment,
            'EDX_ENVIRONMENT': edx_environment,
            'APP_REPO': app_repo,
            'ARTIFACT_PATH': '{}/'.format(constants.ARTIFACT_PATH),
            'HIPCHAT_ROOM': hipchat_room,
            'ANSIBLE_CONFIG': constants.ANSIBLE_CONTINUOUS_DELIVERY_CONFIG,
        }
    )

    stage = pipeline.ensure_stage(constants.RUN_PLAY_STAGE_NAME)
    if manual_approval:
        stage.set_has_manual_approval()

    # Install the requirements.
    job = stage.ensure_job(constants.RUN_PLAY_JOB_NAME)
    tasks.generate_requirements_install(job, 'tubular')
    tasks.generate_requirements_install(job, 'configuration')
    tasks.generate_target_directory(job)

    # fetch the key material
    artifact_params = {
        'pipeline': pipeline.name,
        'stage': constants.LAUNCH_INSTANCE_STAGE_NAME,
        'job': constants.LAUNCH_INSTANCE_JOB_NAME,
        'src': FetchArtifactFile("key.pem"),
        'dest': constants.ARTIFACT_PATH
    }
    job.add_task(FetchArtifactTask(**artifact_params))

    # fetch the launch_info.yml
    artifact_params['src'] = FetchArtifactFile('launch_info.yml')
    job.add_task(FetchArtifactTask(**artifact_params))

    # fetch the inventory file
    artifact_params['src'] = FetchArtifactFile('ansible_inventory')
    job.add_task(FetchArtifactTask(**artifact_params))

    tasks.generate_run_app_playbook(job, configuration_internal_dir, configuration_secure_dir, playbook_with_path, **kwargs)
    return stage


def generate_create_ami_from_instance(pipeline,
                                      play,
                                      deployment,
                                      edx_environment,
                                      app_repo,
                                      configuration_secure_repo,
                                      aws_access_key_id,
                                      aws_secret_access_key,
                                      configuration_repo=constants.PUBLIC_CONFIGURATION_REPO_URL,
                                      ami_creation_timeout="3600",
                                      ami_wait='yes',
                                      cache_id='',
                                      artifact_path=constants.ARTIFACT_PATH,
                                      hipchat_token='',
                                      hipchat_room=constants.HIPCHAT_ROOM,
                                      manual_approval=False,
                                      **kwargs):
    """
    Generates an artifact ami.yml:
        ami_id: ami-abcdefg
        ami_message: AMI creation operation complete
        ami_state: available

    Args:
        pipeline (gomatic.Pipeline):
        play (str): Play that was run on the instance (used for tagging)
        deployment (str):
        edx_environment (str):
        app_repo (str):
        configuration_secure_repo (str):
        aws_access_key_id (str):
        aws_secret_access_key (str):
        configuration_repo (str):
        ami_creation_timeout (str):
        ami_wait (str):
        cache_id (str):
        artifact_path (str):
        hipchat_room (str):
        manual_approval (bool):
        **kwargs (dict):
            k,v pairs:
                k: the name of the option to pass to ansible
                v: the value to use for this option

    Returns:
        gomatic.Stage
    """
    stage = pipeline.ensure_stage(constants.BUILD_AMI_STAGE_NAME)
    if manual_approval:
        stage.set_has_manual_approval()
    pipeline.ensure_encrypted_environment_variables(
        {
            'AWS_ACCESS_KEY_ID': aws_access_key_id,
            'AWS_SECRET_ACCESS_KEY': aws_secret_access_key,
            'HIPCHAT_TOKEN': hipchat_token,
        }
    )

    pipeline.ensure_environment_variables(
        {
            'PLAY': play,
            'DEPLOYMENT': deployment,
            'EDX_ENVIRONMENT': edx_environment,
            'APP_REPO': app_repo,
            'CONFIGURATION_REPO': configuration_repo,
            'CONFIGURATION_SECURE_REPO': configuration_secure_repo,
            'AMI_CREATION_TIMEOUT': ami_creation_timeout,
            'AMI_WAIT': ami_wait,
            'CACHE_ID': cache_id,  # gocd build number
            'ARTIFACT_PATH': artifact_path,
            'HIPCHAT_ROOM': hipchat_room,
            'ANSIBLE_CONFIG': constants.ANSIBLE_CONTINUOUS_DELIVERY_CONFIG,
        }
    )

    # Install the requirements.
    job = stage.ensure_job(constants.BUILD_AMI_JOB_NAME)
    tasks.generate_requirements_install(job, 'tubular')
    tasks.generate_requirements_install(job, 'configuration')

    tasks.generate_target_directory(job)

    # fetch the key material
    artifact_params = {
        'pipeline': pipeline.name,
        'stage': constants.LAUNCH_INSTANCE_STAGE_NAME,
        'job': constants.LAUNCH_INSTANCE_JOB_NAME,
        'src': FetchArtifactFile("launch_info.yml"),
        'dest': constants.ARTIFACT_PATH
    }
    job.add_task(FetchArtifactTask(**artifact_params))

    # Create an AMI from the instance
    tasks.generate_create_ami(job, **kwargs)

    return stage


def generate_deploy_ami(pipeline,
                        asgard_api_endpoints,
                        asgard_token,
                        aws_access_key_id,
                        aws_secret_access_key,
                        upstream_ami_artifact=None,
                        manual_approval=True
                        ):
    """
    Generates a stage which deploys an AMI via Asgard.

    if the variable upstream_ami_artifact is set, information about which AMI to deploy will be pulled
    from this pipeline/stage/file.

    if upstream_ami_artifact is not set, the environment variable AMI_ID will be used to determine what
    AMI to deploy

    Args:
        pipeline (gomatic.Pipeline):
        asgard_api_endpoints (str): canonical URL for asgard.
        asgard_token (str):
        aws_access_key_id (str):
        aws_secret_access_key (str):
        upstream_ami_artifact (ArtifactLocation): The location of yaml artifact that has the `ami_id`
        manual_approval (bool): Should this stage require manual approval?
    Returns:
        gomatic.Stage
    """
    pipeline.ensure_environment_variables(
        {
            'ASGARD_API_ENDPOINTS': asgard_api_endpoints,
            'WAIT_SLEEP_TIME': constants.TUBULAR_SLEEP_WAIT_TIME
        }
    ).ensure_encrypted_environment_variables(
        {
            'ASGARD_API_TOKEN': asgard_token,
            'AWS_ACCESS_KEY_ID': aws_access_key_id,
            'AWS_SECRET_ACCESS_KEY': aws_secret_access_key,
        }
    )

    stage = pipeline.ensure_stage(constants.DEPLOY_AMI_STAGE_NAME)
    if manual_approval:
        stage.set_has_manual_approval()
    job = stage.ensure_job(constants.DEPLOY_AMI_JOB_NAME)
    tasks.generate_requirements_install(job, 'tubular')
    # Make the artifact directory if it does not exist
    job.add_task(ExecTask(
        [
            '/bin/bash',
            '-c',
            'mkdir -p ../{}'.format(constants.ARTIFACT_PATH),
        ],
        working_dir="tubular")
    )

    # Setup the deployment output file
    artifact_path = '{}/{}'.format(
        constants.ARTIFACT_PATH,
        constants.DEPLOY_AMI_OUT_FILENAME
    )
    job.ensure_artifacts(set([BuildArtifact(artifact_path)]))

    deploy_command =\
        '/usr/bin/python ' \
        'scripts/asgard-deploy.py ' \
        '--out_file ../{} '.format(artifact_path)

    if upstream_ami_artifact:
        artifact_params = {
            "pipeline": upstream_ami_artifact.pipeline,
            "stage": upstream_ami_artifact.stage,
            "job": upstream_ami_artifact.job,
            "src": FetchArtifactFile(upstream_ami_artifact.file_name),
            "dest": 'tubular'
        }
        job.add_task(FetchArtifactTask(**artifact_params))
        deploy_command += '--config-file {}'.format(upstream_ami_artifact.file_name)

    else:
        pipeline.ensure_environment_variables({'AMI_ID': None})
        deploy_command += '--ami_id $AMI_ID'

    # Execute the deployment script
    job.add_task(ExecTask(['/bin/bash', '-c', deploy_command], working_dir="tubular"))
    return stage


def generate_edp_validation(pipeline,
                            hipchat_token,
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
        hipchat_token (str):
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
                                           'AMI_PLAY': ami_play}) \
        .ensure_encrypted_environment_variables({'HIPCHAT_TOKEN': hipchat_token})

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
                            inventory_location,
                            instance_key_location,
                            launch_info_location,
                            application_user,
                            application_name,
                            application_path,
                            duration_threshold=None,
                            from_address=None,
                            to_addresses=None,
                            sub_application_name=None,
                            manual_approval=False):
    """
    Generate the stage that applies/runs migrations.

    Args:
        pipeline (gomatic.Pipeline): Pipeline to which to add the run migrations stage.
        db_migration_pass (str): Password for the DB user used to run migrations.
        inventory_location (ArtifactLocation): Location of inventory containing the IP address of the EC2 instance, for fetching.
        instance_key_location (ArtifactLocation): Location of SSH key used to access the EC2 instance, for fetching.
        launch_info_location (ArtifactLocation): Location of the launch_info.yml file for fetching
        application_user (str): Username to use while running the migrations
        application_name (str): Name of the application (e.g. edxapp, programs, etc...)
        application_path (str): path of the application installed on the target machine
        duration_threshold (int): Threshold in seconds over which a migration duration will be alerted.
        from_address (str): Any migration duration email alert will be from this address.
        to_addresses (list(str)): List of To: addresses for migration duration email alerts.
        sub_application_name (str): any sub application to insert in to the migrations commands {cms|lms}
        manual_approval (bool): Should this stage require manual approval?

    Returns:
        gomatic.Stage
    """
    pipeline.ensure_environment_variables(
        {
            'APPLICATION_USER': application_user,
            'APPLICATION_NAME': application_name,
            'APPLICATION_PATH': application_path,
            'DB_MIGRATION_USER': 'migrate',
            'ARTIFACT_PATH': constants.ARTIFACT_PATH,
            'ANSIBLE_CONFIG': constants.ANSIBLE_CONTINUOUS_DELIVERY_CONFIG
        }
    )
    if duration_threshold:
        pipeline.ensure_environment_variables(
            {
                'MAX_EMAIL_TRIES': constants.MAX_EMAIL_TRIES
            }
        )
    pipeline.ensure_encrypted_environment_variables(
        {
            'DB_MIGRATION_PASS': db_migration_pass,
        }
    )

    if sub_application_name is not None:
        stage_name = "{}_{}".format(constants.APPLY_MIGRATIONS_STAGE, sub_application_name)
    else:
        stage_name = constants.APPLY_MIGRATIONS_STAGE
    stage = pipeline.ensure_stage(stage_name)

    if manual_approval:
        stage.set_has_manual_approval()
    job = stage.ensure_job(constants.APPLY_MIGRATIONS_JOB)

    # Fetch the Ansible inventory to use in reaching the EC2 instance.
    artifact_params = {
        "pipeline": inventory_location.pipeline,
        "stage": inventory_location.stage,
        "job": inventory_location.job,
        "src": FetchArtifactFile(inventory_location.file_name),
        "dest": constants.ARTIFACT_PATH
    }
    job.add_task(FetchArtifactTask(**artifact_params))

    # Fetch the SSH key to use in reaching the EC2 instance.
    artifact_params = {
        "pipeline": instance_key_location.pipeline,
        "stage": instance_key_location.stage,
        "job": instance_key_location.job,
        "src": FetchArtifactFile(instance_key_location.file_name),
        "dest": constants.ARTIFACT_PATH
    }
    job.add_task(FetchArtifactTask(**artifact_params))

    # ensure the target directoy exists
    tasks.generate_target_directory(job)

    # fetch the launch_info.yml
    artifact_params = {
        "pipeline": launch_info_location.pipeline,
        "stage": launch_info_location.stage,
        "job": launch_info_location.job,
        "src": FetchArtifactFile(launch_info_location.file_name),
        "dest": constants.ARTIFACT_PATH
    }
    job.add_task(FetchArtifactTask(**artifact_params))

    # The SSH key used to access the EC2 instance needs specific permissions.
    job.add_task(
        ExecTask(
            ['/bin/bash', '-c', 'chmod 600 {}'.format(instance_key_location.file_name)],
            working_dir=constants.ARTIFACT_PATH
        )
    )

    tasks.generate_requirements_install(job, 'configuration')
    tasks.generate_run_migrations(job, sub_application_name)

    if duration_threshold:
        tasks.generate_check_migration_duration(
            job,
            constants.MIGRATION_RESULT_FILENAME,
            duration_threshold,
            from_address,
            to_addresses
        )

    # Cleanup EC2 instance if running the migrations failed.
    # I think this should be left for the terminate instance stage
    # tasks.generate_ami_cleanup(job, runif='failed')

    return stage


def generate_terminate_instance(pipeline,
                                instance_info_location,
                                aws_access_key_id,
                                aws_secret_access_key,
                                hipchat_token,
                                ec2_region=constants.EC2_REGION,
                                artifact_path=constants.ARTIFACT_PATH,
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
    pipeline.ensure_encrypted_environment_variables(
        {
            'AWS_ACCESS_KEY_ID': aws_access_key_id,
            'AWS_SECRET_ACCESS_KEY': aws_secret_access_key,
            'HIPCHAT_TOKEN': hipchat_token
        }
    )
    pipeline.ensure_environment_variables(
        {
            'ARTIFACT_PATH': artifact_path,
            'EC2_REGION': ec2_region,
            'HIPCHAT_ROOM': constants.HIPCHAT_ROOM
        }
    )

    stage = pipeline.ensure_stage(constants.TERMINATE_INSTANCE_STAGE_NAME)
    if manual_approval:
        stage.set_has_manual_approval()

    # Fetch the instance info to use in reaching the EC2 instance.
    artifact_params = {
        'pipeline': instance_info_location.pipeline,
        'stage': instance_info_location.stage,
        'job': instance_info_location.job,
        'src': FetchArtifactFile(instance_info_location.file_name),
        'dest': constants.ARTIFACT_PATH
    }
    job = stage.ensure_job(constants.TERMINATE_INSTANCE_JOB_NAME)
    tasks.generate_requirements_install(job, 'configuration')
    job.add_task(FetchArtifactTask(**artifact_params))

    tasks.generate_ami_cleanup(job, runif=runif)

    return stage


def generate_rollback_asg_stage(
    pipeline,
    asgard_api_endpoints,
    asgard_token,
    aws_access_key_id,
    aws_secret_access_key,
    hipchat_token,
    hipchat_room,
    deploy_file_location
):
    """
    Generates a stage which performs rollback to a previous ASG (or ASGs) via Asgard.
    If the previous ASG (or ASGs) fail health checks for some reason, a new ASGs with
    the provided AMI ID is created and used as the rollback ASG(s).
    This stage *always* requires manual approval.

    Args:
        pipeline (gomatic.Pipeline):
        asgard_api_endpoints (str): canonical URL for asgard.
        asgard_token (str):
        aws_access_key_id (str):
        aws_secret_access_key (str):
        deploy_file_location (ArtifactLocation): The location of YAML artifact from the previous deploy
            that has the previous ASG info along with `ami_id`, for rollback/re-deploy respectively.
    Returns:
        gomatic.Stage
    """
    pipeline.ensure_environment_variables(
        {
            'ASGARD_API_ENDPOINTS': asgard_api_endpoints,
            'HIPCHAT_ROOM': hipchat_room,
        }
    )
    pipeline.ensure_encrypted_environment_variables(
        {
            'ASGARD_API_TOKEN': asgard_token,
            'AWS_ACCESS_KEY_ID': aws_access_key_id,
            'AWS_SECRET_ACCESS_KEY': aws_secret_access_key,
            'HIPCHAT_TOKEN': hipchat_token,
        }
    )

    stage = pipeline.ensure_stage(constants.ROLLBACK_ASGS_STAGE_NAME)
    # Important: Do *not* automatically rollback! Always manual...
    stage.set_has_manual_approval()
    job = stage.ensure_job(constants.ROLLBACK_ASGS_JOB_NAME)
    tasks.generate_requirements_install(job, 'tubular')

    artifact_params = {
        "pipeline": deploy_file_location.pipeline,
        "stage": deploy_file_location.stage,
        "job": deploy_file_location.job,
        "src": FetchArtifactFile(deploy_file_location.file_name),
        "dest": 'tubular'
    }
    job.add_task(FetchArtifactTask(**artifact_params))

    job.add_task(ExecTask(
        [
            '/bin/bash',
            '-c',
            'mkdir -p ../target',
        ],
        working_dir="tubular")
    )

    artifact_path = '{}/{}'.format(
        constants.ARTIFACT_PATH,
        constants.ROLLBACK_AMI_OUT_FILENAME
    )
    job.ensure_artifacts(set([BuildArtifact(artifact_path)]))

    job.add_task(ExecTask(
        [
            '/usr/bin/python',
            'scripts/rollback_asg.py',
            '--config_file', deploy_file_location.file_name,
            '--out_file', '../{}'.format(artifact_path),
        ],
        working_dir="tubular")
    )
    return stage


def generate_ansible_stage(
    stage_name,
    task,
    pipeline,
    inventory_location,
    instance_key_location,
    launch_info_location,
    application_user,
    application_name,
    application_path,
    hipchat_token,
    hipchat_room=constants.HIPCHAT_ROOM,
    manual_approval=False
):
    """
        Generate the stage with the given name, that runs the specified task.

        Args:
            stage_name (str): Name of the generated stage.
            task (function): Task to be executed by the stage.
            pipeline (gomatic.Pipeline): Pipeline to which to add the run migrations stage.
            inventory_location (ArtifactLocation): Location of inventory containing the IP address of the EC2 instance, for fetching.
            instance_key_location (ArtifactLocation): Location of SSH key used to access the EC2 instance, for fetching.
            launch_info_location (ArtifactLocation): Location of the launch_info.yml file for fetching
            application_user (str): Username to use while running the migrations
            application_name (str): Name of the application (e.g. edxapp, programs, etc...)
            application_path (str): path of the application installed on the target machine
            hipchat_token (str): HipChat authentication token
            hipchat_room (str): HipChat room where announcements should be made
            manual_approval (bool): Should this stage require manual approval?

        Returns:
            gomatic.Stage
        """

    pipeline.ensure_environment_variables(
        {
            'APPLICATION_USER': application_user,
            'APPLICATION_NAME': application_name,
            'APPLICATION_PATH': application_path,
            'HIPCHAT_ROOM': hipchat_room,
        }
    )
    pipeline.ensure_encrypted_environment_variables(
        {
            'HIPCHAT_TOKEN': hipchat_token,
        }
    )

    stage = pipeline.ensure_stage(stage_name)

    if manual_approval:
        stage.set_has_manual_approval()
    job = stage.ensure_job(stage_name + '_job')

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
        "pipeline": launch_info_location.pipeline,
        "stage": launch_info_location.stage,
        "job": launch_info_location.job,
        "src": FetchArtifactFile(launch_info_location.file_name),
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
    task(job)

    return stage


def generate_refresh_metadata(
    pipeline,
    inventory_location,
    instance_key_location,
    launch_info_location,
    application_user,
    application_name,
    application_path,
    hipchat_token='',
    hipchat_room=constants.HIPCHAT_ROOM,
    manual_approval=False
):
    """
    Generate the stage that refreshes metadata for the discovery service.

    Args:
        pipeline (gomatic.Pipeline): Pipeline to which to add the run migrations stage.
        inventory_location (ArtifactLocation): Location of inventory containing the IP address of the EC2 instance, for fetching.
        instance_key_location (ArtifactLocation): Location of SSH key used to access the EC2 instance, for fetching.
        launch_info_location (ArtifactLocation): Location of the launch_info.yml file for fetching
        application_user (str): Username to use while running the migrations
        application_name (str): Name of the application (e.g. edxapp, programs, etc...)
        application_path (str): path of the application installed on the target machine
        hipchat_token (str): HipChat authentication token
        hipchat_room (str): HipChat room where announcements should be made
        manual_approval (bool): Should this stage require manual approval?

    Returns:
        gomatic.Stage
    """
    return generate_ansible_stage(
        'refresh_metadata',
        tasks.generate_refresh_metadata,
        pipeline,
        inventory_location,
        instance_key_location,
        launch_info_location,
        application_user,
        application_name,
        application_path,
        hipchat_token,
        hipchat_room,
        manual_approval
    )


def generate_update_index(
    pipeline,
    inventory_location,
    instance_key_location,
    launch_info_location,
    application_user,
    application_name,
    application_path,
    hipchat_token='',
    hipchat_room=constants.HIPCHAT_ROOM,
    manual_approval=False
):
    """
    Generate the stage that refreshes metadata for the discovery service.

    Args:
        pipeline (gomatic.Pipeline): Pipeline to which to add the run migrations stage.
        inventory_location (ArtifactLocation): Location of inventory containing the IP address of the EC2 instance, for fetching.
        instance_key_location (ArtifactLocation): Location of SSH key used to access the EC2 instance, for fetching.
        launch_info_location (ArtifactLocation): Location of the launch_info.yml file for fetching
        application_user (str): Username to use while running the migrations
        application_name (str): Name of the application (e.g. edxapp, programs, etc...)
        application_path (str): path of the application installed on the target machine
        hipchat_token (str): HipChat authentication token
        hipchat_room (str): HipChat room where announcements should be made
        manual_approval (bool): Should this stage require manual approval?

    Returns:
        gomatic.Stage
    """
    return generate_ansible_stage(
        'update_index',
        tasks.generate_update_index,
        pipeline,
        inventory_location,
        instance_key_location,
        launch_info_location,
        application_user,
        application_name,
        application_path,
        hipchat_token,
        hipchat_room,
        manual_approval
    )


def generate_armed_stage(pipeline, stage_name):
    """
    Generates a stage that can be used to "arm" a pipeline.

    When using a fan in or fan out GoCD will ensure the consistency of materials used between pipelines. To accomplish
     this all pipelines must be set to to trigger on success. This stage generates a simple echo statement that can
     be used to "arm" a pipeline. The stage that follows this must set the manual_approval flag via:
     set_has_manual_approval()

    Using this pattern allows a pipeline to be be set as automatic, but then pause and wait for input from the user.

    Args:
        pipeline (gomatic.Pipeline): Pipeline to which to add this stage.
        stage_name (str): Name of the stage.

    Returns:
        gomatic.Stage
    """
    armed_stage = pipeline.ensure_stage(stage_name)
    armed_job = armed_stage.ensure_job(constants.ARMED_JOB_NAME)
    armed_job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                'echo Pipeline run number $GO_PIPELINE_COUNTER armed by $GO_TRIGGER_USER'
            ],
        )
    )

    return armed_stage


def generate_create_pr_stage(pipeline,
                             stage_name,
                             org,
                             repo,
                             source_branch,
                             target_branch,
                             pr_target_branch,
                             token):
    """
    Generates a stage that is used to:
    - Create a branch (target_branch) from the source branch's head revision

    create a PR for a release.
    Args:
        pipeline (gomatic.Pipeline): Pipeline to attach this stage to
        stage_name (str): Name of the stage
        org (str): Name of the github organization that holds the repository (e.g. edx)
        repo (str): Name of repository (e.g edx-platform)
        source_branch (str): Name of the branch to create the branch/PR from
        target_branch (str): Name of the branch to be created (will be the head of the PR)
        pr_target_branch (str): The base branch of the pull request (merge target_branch in to pr_target_branch)
        token (str): the github token used to create all these things. Will be an env_var 'GIT_TOKEN'

    Returns:
        gomatic.Stage
    """
    pipeline.ensure_unencrypted_secure_environment_variables(
        {
            'GIT_TOKEN': token
        }
    )
    git_stage = pipeline.ensure_stage(stage_name)
    git_job = git_stage.ensure_job(constants.GIT_SETUP_JOB_NAME)
    tasks.generate_target_directory(git_job)
    tasks.generate_create_release_candidate_branch_and_pr(
        git_job,
        org,
        repo,
        source_branch,
        target_branch,
        pr_target_branch
    )

    return git_stage


def generate_create_branch(pipeline,
                           stage_name,
                           org,
                           repo,
                           target_branch,
                           token,
                           manual_approval,
                           source_branch=None,
                           sha=None):
    """
    Generates a stage that is used to:
    - Create a branch (target_branch) from the source branch's head revision, will select the latest merge commit that
    has passed CI.

    Args:
        pipeline (gomatic.Pipeline): Pipeline to attach this stage
        stage_name (str): Name of the stage
        org (str): Name of the github organization that holds the repository (e.g. edx)
        repo (str): Name of repository (e.g edx-platform)
        target_branch (str): Name of the branch to be created (will be the head of the PR)
        token (str): the github token used to create all these things. Will be an env_var 'GIT_TOKEN'
        manual_approval (bool): Should this stage require manual approval?
        source_branch (str): Name (or environment variable) of the branch to create the branch/PR from
        sha (str): SHA (or environment variable) of the commit to create the branch/PR from


    Returns:
        gomatic.Stage
    """
    pipeline.ensure_unencrypted_secure_environment_variables(
        {
            'GIT_TOKEN': token
        }
    )
    git_stage = pipeline.ensure_stage(stage_name)
    if manual_approval:
        git_stage.set_has_manual_approval()
    git_job = git_stage.ensure_job(constants.GIT_CREATE_BRANCH_JOB_NAME)
    tasks.generate_target_directory(git_job)
    tasks.generate_create_branch(
        git_job,
        org,
        repo,
        target_branch,
        source_branch=source_branch,
        sha=sha,
    )

    return git_stage


def generate_deployment_messages(
        pipeline, prod_build_pipelines, stage_deploy_pipeline, org,
        repo, token, head_sha, release_status, confluence_user, confluence_password,
        github_token, manual_approval=False,
        base_sha=None, base_ami_artifact=None, ami_tag_app=None,
        wiki_parent_title=None, wiki_space=None, wiki_title=None
):
    """
    Creates a stage that will message the pull requests for a range of commits that the respective pull requests have
    been deployed to the staging environment.

    Args:
        pipeline (gomatic.Pipeline): Pipeline to attach this stage
        prod_build_pipelines (list of gomatic.Pipeline): The build pipelines that produced the AMIs being deployed
        stage_deploy_pipeline: The pipeline that deployed to staging
        org (str): Name of the github organization that holds the repository (e.g. edx)
        repo (str): Name of repository (e.g edx-platform)
        token (str): the github token used to create all these things. Will be an env_var 'GIT_TOKEN'
        head_sha(str): ending SHA or environment variable holding the SHA to start the commit range
        release_status (ReleaseStatus): the current status of the release
        confluence_user (str): The confluence user to create the release page with
        confluence_password (str): The confluence password to create the release page with
        github_token (str): The github token to fetch PR data with
        manual_approval (bool): Should this stage require manual approval?
        base_sha (str): The sha to use as the base point for sending messages
            (any commits prior to this sha won't be messaged). (Optional)
        base_ami_artifact (ArtifactLocation): The location of the artifact that specifies
            the base_ami and tags (Optional)
        ami_tag_app (str): The name of the version tag on the AMI to extract the version from (Optional)
        wiki_parent_title (str): The title of the parent page to publish the release page under (defaults to 'LMS/Studio Release Pages')
        wiki_space (str): The space to publish the release page in (defaults to 'ENG')
        wiki_title (str): The title of the release wiki page (defaults to '<Next Release Date> Release')

    Returns:
        gomatic.stage.Stage

    """
    message_stage = pipeline.ensure_stage(constants.MESSAGE_PR_STAGE_NAME)
    if manual_approval:
        message_stage.set_has_manual_approval()
    message_job = message_stage.ensure_job(constants.MESSAGE_PR_JOB_NAME)
    tasks.generate_message_pull_requests_in_commit_range(
        message_job, org, repo, token, head_sha, release_status,
        base_sha=base_sha, base_ami_artifact=base_ami_artifact, ami_tag_app=ami_tag_app
    )
    wiki_job = message_stage.ensure_job(constants.PUBLISH_WIKI_JOB_NAME)

    if release_status == ReleaseStatus.STAGED:
        parent_title = wiki_parent_title
        title = wiki_title
        space = wiki_space
        input_artifact = None
    else:
        parent_title = None
        title = None
        space = None
        input_artifact = ArtifactLocation(
            stage_deploy_pipeline.name,
            message_stage.name,
            constants.PUBLISH_WIKI_JOB_NAME,
            constants.RELEASE_WIKI_PAGE_ID_FILENAME,
        )

    ami_pairs = [
        (
            ArtifactLocation(
                build_pipeline.name,
                constants.BASE_AMI_SELECTION_STAGE_NAME,
                constants.BASE_AMI_SELECTION_JOB_NAME,
                constants.BASE_AMI_OVERRIDE_FILENAME,
            ),
            ArtifactLocation(
                build_pipeline.name,
                constants.BUILD_AMI_STAGE_NAME,
                constants.BUILD_AMI_JOB_NAME,
                constants.BUILD_AMI_FILENAME,
            )
        ) for build_pipeline in prod_build_pipelines
    ]

    tasks.generate_release_wiki_page(
        pipeline,
        wiki_job,
        confluence_user=confluence_user,
        confluence_password=confluence_password,
        github_token=github_token,
        release_status=release_status,
        ami_pairs=ami_pairs,
        parent_title=parent_title,
        space=space,
        title=title,
        input_artifact=input_artifact,
    )

    return message_stage


def generate_merge_branch_and_tag(pipeline,
                                  stage_name,
                                  deploy_artifact,
                                  org,
                                  repo,
                                  target_branch,
                                  head_sha,
                                  token,
                                  fast_forward_only,
                                  manual_approval):
    """
    Generates a stage that is used to:
    - Merge a Git source branch into a target branch, optionally ensuring that the merge is a fast-forward merge.
    - Tag a release SHA.

    Args:
        pipeline (gomatic.Pipeline): Pipeline to which this stage will be attached
        stage_name (str): Name of the stage
        deploy_artifact (ArtifactLocation): Location of deployment artifact file
        org (str): Name of the github organization that holds the repository (e.g. edx)
        repo (str): Name of repository (e.g edx-platform)
        target_branch (str): Name of the branch into which to merge the source branch
        head_sha (str): commit SHA or environment variable holding the SHA to tag as the release
        token (str): the github token used to create all these things. Will be an env_var 'GIT_TOKEN'
        fast_forward_only (bool): If True, force a fast-forward merge or fail.
        manual_approval (bool): Should this stage require manual approval?

    Returns:
        gomatic.Stage
    """
    pipeline.ensure_unencrypted_secure_environment_variables(
        {
            'GIT_TOKEN': token
        }
    )
    git_stage = pipeline.ensure_stage(stage_name)
    if manual_approval:
        git_stage.set_has_manual_approval()

    merge_branch_job = git_stage.ensure_job(constants.GIT_MERGE_RC_BRANCH_JOB_NAME)
    tasks.generate_target_directory(merge_branch_job)
    tasks.generate_merge_branch(
        merge_branch_job,
        org,
        repo,
        head_sha,
        target_branch,
        fast_forward_only
    )

    # Generate a job/task which tags the head commit of the source branch.
    # Instruct the task to auto-generate tag name/message by not sending them in.
    tag_job = git_stage.ensure_job(constants.GIT_TAG_SHA_JOB_NAME)

    if deploy_artifact:
        # Fetch the AMI-deployment artifact to extract deployment time.
        tag_job.add_task(
            FetchArtifactTask(
                pipeline=deploy_artifact.pipeline,
                stage=deploy_artifact.stage,
                job=deploy_artifact.job,
                src=FetchArtifactFile(deploy_artifact.file_name),
                dest=constants.ARTIFACT_PATH
            )
        )

    tasks.generate_tag_commit(
        tag_job,
        org,
        repo,
        commit_sha=head_sha,
        deploy_artifact_filename=deploy_artifact.file_name if deploy_artifact else None
    )


def generate_create_branch_and_pr(pipeline,
                                  stage_name,
                                  org,
                                  repo,
                                  source_branch,
                                  new_branch,
                                  target_branch,
                                  pr_title,
                                  pr_body,
                                  token,
                                  manual_approval):
    """
    Generates a stage that is used to:
    - create a new branch off the HEAD of a source branch
    - create a PR to merge the new branch into a target branch

    Args:
        pipeline (gomatic.Pipeline): Pipeline to attach this stage to
        stage_name (str): Name of the stage
        org (str): Name of the github organization that holds the repository (e.g. edx)
        repo (str): Name of repository (e.g edx-platform)
        source_branch (str): Name of the branch to use in creating the new branch
        new_branch (str): Name of the branch to create off the HEAD of the source branch
        target_branch (str): Name of the branch into which to merge the source branch
        pr_title (str): Title of the new PR
        pr_body (str): Body of the new PR
        token (str): the github token used to create all these things. Will be an env_var 'GIT_TOKEN'
        manual_approval (bool): Should this stage require manual approval?

    Returns:
        gomatic.Stage
    """
    pipeline.ensure_unencrypted_secure_environment_variables(
        {
            'GIT_TOKEN': token
        }
    )
    git_stage = pipeline.ensure_stage(stage_name)
    if manual_approval:
        git_stage.set_has_manual_approval()
    git_job = git_stage.ensure_job(constants.CREATE_MASTER_MERGE_PR_JOB_NAME)
    tasks.generate_target_directory(git_job)

    # Generate a task that creates a new branch off the HEAD of a source branch.
    tasks.generate_create_branch(
        git_job,
        org,
        repo,
        target_branch=new_branch,
        source_branch=source_branch
    )

    # Generate a task that creates a pull request merging the new branch from above into a target branch.
    tasks.generate_create_pr(
        git_job,
        org,
        repo,
        new_branch,
        target_branch,
        pr_title,
        pr_body
    )

    return git_stage


def generate_poll_tests_and_merge_pr(pipeline,
                                     stage_name,
                                     org,
                                     repo,
                                     token,
                                     initial_poll_wait,
                                     max_poll_tries,
                                     poll_interval,
                                     manual_approval):
    """
    Generates a stage that is used to:
    - poll for successful completion of PR tests
    - merge the PR

    Args:
        pipeline (gomatic.Pipeline): Pipeline to attach this stage to
        stage_name (str): Name of the stage
        org (str): Name of the github organization that holds the repository (e.g. edx)
        repo (str): Name of repository (e.g edx-platform)
        token (str): the github token used to create all these things. Will be an env_var 'GIT_TOKEN'
        manual_approval (bool): Should this stage require manual approval?

    Returns:
        gomatic.Stage
    """
    pipeline.ensure_environment_variables(
        {
            'PR_TEST_INITIAL_WAIT_INTERVAL': str(initial_poll_wait),
            'MAX_PR_TEST_POLL_TRIES': str(max_poll_tries),
            'PR_TEST_POLL_INTERVAL': str(poll_interval)
        }
    )
    pipeline.ensure_unencrypted_secure_environment_variables(
        {
            'GIT_TOKEN': token
        }
    )
    git_stage = pipeline.ensure_stage(stage_name)
    if manual_approval:
        git_stage.set_has_manual_approval()
    git_job = git_stage.ensure_job(constants.CHECK_PR_TESTS_AND_MERGE_JOB_NAME)

    # Fetch the PR-creation material.
    git_job.add_task(
        FetchArtifactTask(
            pipeline=pipeline.name,
            stage=constants.CREATE_MASTER_MERGE_PR_STAGE_NAME,
            job=constants.CREATE_MASTER_MERGE_PR_JOB_NAME,
            src=FetchArtifactFile(constants.CREATE_BRANCH_PR_FILENAME),
            dest=constants.ARTIFACT_PATH
        )
    )

    # Generate a task that poll the status of combined tests for a PR.
    tasks.generate_poll_pr_tests(
        git_job,
        org,
        repo,
        constants.CREATE_BRANCH_PR_FILENAME
    )

    # Generate a task that merges a PR that has passed all its tests in the previous task.
    tasks.generate_merge_pr(
        git_job,
        org,
        repo,
        constants.CREATE_BRANCH_PR_FILENAME
    )

    return git_stage


def generate_build_value_stream_map_url(pipeline):
    """
    Genrates a stage that is used to build and serialize the value_stream_map url for a pipeline.

    Generates 1 artifact:
        value_stream_map.yaml   - YAML file that contains the value_stream_map URL.

    Args:
        pipeline (gomatic.Pipeline):

    Returns:
        gomatic.Stage
    """
    # Create the stage
    stage = pipeline.ensure_stage(constants.BUILD_VALUE_STREAM_MAP_URL_STAGE_NAME)

    # Create the job
    job = stage.ensure_job(constants.BUILD_VALUE_STREAM_MAP_URL_JOB_NAME)

    # Add task to generate the directory where the value_stream_map.yaml file will be written.
    tasks.generate_target_directory(job)

    # Add task to upload the value_stream_map.yaml file.
    value_stream_map_filepath = '{artifact_path}/{file_name}'.format(
        artifact_path=constants.ARTIFACT_PATH,
        file_name=constants.VALUE_STREAM_MAP_FILENAME
    )
    job.ensure_artifacts(set([value_stream_map_filepath]))

    # Script to generate the value_stream_map_url and write it out to value_stream_map.yaml
    script = '''
        if [ -z "$GO_PIPELINE_NAME" ] || [ -z "$GO_PIPELINE_LABEL" ]; then
          echo "Error: missing GO_PIPELINE_NAME and/or GO_PIPELINE_LABEL" 1>&2
          exit 1
        fi
        printf -- '---\n- deploy_value_stream_map: "{base_url}/$GO_PIPELINE_NAME/$GO_PIPELINE_LABEL"' > {filepath}
    '''.format(base_url=constants.BASE_VALUE_STREAM_MAP_URL, filepath=value_stream_map_filepath)
    job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                script
            ]
        )
    )

    return stage
