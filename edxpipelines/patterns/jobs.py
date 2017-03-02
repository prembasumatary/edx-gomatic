"""
Common gomatic Jobs patterns.

Responsibilities:
    Job patterns should ...
        * return the created job (or a dict of jobs, if there are more than one).
        * expect ArtifactLocations as input.
            * It's the responsibility of the stage/pipeline to ensure that the
              supplied artifacts don't refer to a job in the same stage.
        * use constants for job names.
        * not specify environment variables (leave that to tasks).
        * only be used for common groupings of tasks that need to be parameterized
          (task patterns can be used directly from stage patterns or pipeline patterns).
        * ``ensure`` the scm materials needed for any non-pattern task to function.
"""
import edxpipelines.constants as constants
import edxpipelines.patterns.tasks as tasks
from edxpipelines.utils import ArtifactLocation, path_to_artifact


def generate_build_ami(stage,
                       edp,
                       app_repo_url,
                       configuration_secure_material,
                       configuration_internal_material,
                       playbook_path,
                       env_config,
                       **kwargs):
    """
    Generates a job for creating a new AMI.

    Args:
        stage (gomatic.gocd.pipelines.Stage): Stage to which this job belongs.
        edp (edxpipelines.utils.EDP): Tuple indicating environment, deployment, and play
            for which an AMI will be created.
        app_repo_url (str): App repo's URL.
        configuration_secure_material (gomatic.gomatic.gocd.materials.GitMaterial): Secure
            configuration material. Destination directory expected to be 'configuration-secure'.
        configuration_internal_material (gomatic.gomatic.gocd.materials.GitMaterial): Internal
            configuration material. Destination directory expected to be 'configuration-internal'.
        playbook_path (str): Path to the Ansible playbook to run when creating the AMI.
        env_config (dict): Environment-specific secure config.

    Returns:
        gomatic.gocd.pipelines.Job
    """
    job = stage.ensure_job(constants.BUILD_AMI_JOB_NAME_TPL(edp))

    tasks.generate_requirements_install(job, 'configuration')
    tasks.generate_package_install(job, 'tubular')
    tasks.generate_target_directory(job)

    # Locate the base AMI.
    tasks.generate_base_ami_selection(
        job,
        env_config['aws_access_key_id'],
        env_config['aws_secret_access_key'],
        edx_environment=edp.environment,
        deployment=edp.deployment,
        play=edp.play,
    )

    # Launch a new instance on which to build the AMI.
    tasks.generate_launch_instance(
        job,
        aws_access_key_id=env_config['aws_access_key_id'],
        aws_secret_access_key=env_config['aws_secret_access_key'],
        ec2_vpc_subnet_id=env_config['ec2_vpc_subnet_id'],
        ec2_security_group_id=env_config['ec2_security_group_id'],
        ec2_instance_profile_name=env_config['ec2_instance_profile_name'],
        variable_override_path=path_to_artifact(constants.BASE_AMI_OVERRIDE_FILENAME),
    )

    # Run the Ansible play for the service.
    tasks.generate_run_app_playbook(
        job,
        playbook_path,
        edp,
        app_repo_url,
        private_github_key=env_config['github_private_key'],
        hipchat_token=env_config['hipchat_token'],
        configuration_secure_dir=configuration_secure_material.destination_directory,
        configuration_internal_dir=configuration_internal_material.destination_directory,
        disable_edx_services='true',
        COMMON_TAG_EC2_INSTANCE='true',
        **kwargs
    )

    # Create an AMI from the instance.
    tasks.generate_create_ami(
        job,
        edp.play,
        edp.deployment,
        edp.environment,
        app_repo_url,
        configuration_secure_material.url,
        env_config['aws_access_key_id'],
        env_config['aws_secret_access_key'],
        path_to_artifact(constants.LAUNCH_INSTANCE_FILENAME),
        configuration_secure_version=constants.CONFIGURATION_SECURE_VERSION,
        hipchat_token=env_config['hipchat_token'],
        **kwargs
    )

    tasks.generate_ami_cleanup(job, env_config['hipchat_token'], runif='any')

    return job


def generate_deploy_ami(pipeline, stage, edp, env_config):
    """
    Generates a job for deploying an AMI. Migrations are applied as part of this job.

    Args:
        pipeline (gomatic.gocd.pipelines.Pipeline): Pipeline to which this job belongs.
        stage (gomatic.gocd.pipelines.Stage): Stage to which this job belongs.
        edp (edxpipelines.utils.EDP): Tuple indicating environment, deployment, and play
            to which the AMI belongs.
        env_config (dict): Environment-specific secure config.

    Returns:
        gomatic.gocd.pipelines.Job
    """
    job = stage.ensure_job(constants.DEPLOY_AMI_JOB_NAME_TPL(edp))

    tasks.generate_requirements_install(job, 'configuration')
    tasks.generate_package_install(job, 'tubular')
    tasks.generate_target_directory(job)

    # Retrieve the AMI ID from the upstream build stage.
    ami_artifact_location = ArtifactLocation(
        pipeline.name,
        constants.BUILD_AMIS_STAGE_NAME,
        constants.BUILD_AMI_JOB_NAME_TPL(edp),
        constants.BUILD_AMI_FILENAME
    )
    tasks.retrieve_artifact(ami_artifact_location, job)
    variable_override_path = path_to_artifact(ami_artifact_location.file_name)

    tasks.generate_launch_instance(
        job,
        aws_access_key_id=env_config['aws_access_key_id'],
        aws_secret_access_key=env_config['aws_secret_access_key'],
        ec2_vpc_subnet_id=env_config['ec2_vpc_subnet_id'],
        ec2_security_group_id=env_config['ec2_security_group_id'],
        ec2_instance_profile_name=env_config['ec2_instance_profile_name'],
        variable_override_path=variable_override_path,
    )

    # SSH key used to access the instance needs specific permissions.
    job.ensure_task(tasks.bash_task(
        'chmod 600 {key_pem_path}',
        key_pem_path=path_to_artifact(constants.KEY_PEM_FILENAME)
    ))

    tasks.generate_run_migrations(
        job,
        application_user=edp.play,
        application_name=edp.play,
        application_path='/edx/app/{}'.format(edp.play),
        db_migration_user=constants.DB_MIGRATION_USER,
        db_migration_pass=env_config['db_migration_pass'],
    )

    tasks.generate_deploy_ami(
        job,
        variable_override_path,
        env_config['asgard_api_endpoints'],
        env_config['asgard_token'],
    )

    tasks.generate_ami_cleanup(job, env_config['hipchat_token'], runif='any')

    return job


def generate_rollback_asgs(pipeline, deploy_stage, rollback_stage, edp, config):
    """
    Generates a job for rolling back ASGs (code).

    Args:
        pipeline (gomatic.gocd.pipelines.Pipeline): Pipeline to which this job belongs.
        deploy_stage (gomatic.gocd.pipelines.Stage): Upstream deploy stage from which to
            retrieve deploy info.
        rollback_stage (gomatic.gocd.pipelines.Stage): Stage to which this job belongs.
        edp (edxpipelines.utils.EDP): Tuple indicating environment, deployment, and play
            on which to operate.
        config (dict): Environment-independent secure config.

    Returns:
        gomatic.gocd.pipelines.Job
    """
    job_name = '{environment}_{base_job_name}'.format(
        environment=edp.environment,
        base_job_name=constants.ROLLBACK_ASGS_JOB_NAME
    )
    job = rollback_stage.ensure_job(job_name)

    tasks.generate_package_install(job, 'tubular')
    tasks.generate_target_directory(job)

    # Retrieve build info from the upstream deploy stage.
    deployment_artifact_location = ArtifactLocation(
        pipeline.name,
        deploy_stage.name,
        constants.DEPLOY_AMI_JOB_NAME_TPL(edp),
        constants.DEPLOY_AMI_OUT_FILENAME
    )
    tasks.retrieve_artifact(deployment_artifact_location, job)
    deployment_artifact_path = path_to_artifact(deployment_artifact_location.file_name)

    tasks.generate_rollback_asg(
        job,
        deployment_artifact_path,
        config['asgard_api_endpoints'],
        config['asgard_token'],
    )

    return job


def generate_rollback_migrations(
        stage,
        application_user,
        application_name,
        application_path,
        db_migration_user,
        db_migration_pass,
        pipeline=None,
        deploy_stage=None,
        edp=None,
        inventory_location=None,
        instance_key_location=None,
        migration_info_location=None,
        sub_application_name=None
):
    """
    Generates a job for rolling back database migrations.

    Args:
        stage (gomatic.gocd.pipelines.Stage): Stage this job will be part of
        pipeline (gomatic.gocd.pipelines.Pipeline): Pipeline to which this job belongs.
        deploy_stage (gomatic.gocd.pipelines.Stage): Upstream deploy stage from which to
            retrieve deploy info.
        edp (edxpipelines.utils.EDP): Tuple indicating environment, deployment, and play
            on which to operate.
        inventory_location (utils.ArtifactLocation): Location of the ansible inventory location
        instance_key_location (utils.ArtifactLocation): Location of key used to ssh in to the instance
        migration_info_location (utils.ArtifactLocation): Location of the migration output to roll back
        sub_application_name (str): additional command to be passed to the migrate app {cms|lms}

    Returns:
        gomatic.gocd.pipelines.Job
    """
    if edp:
        job_name = '{environment}_{base_job_name}'.format(
            environment=edp.environment,
            base_job_name=constants.ROLLBACK_MIGRATIONS_JOB_NAME
        )
    else:
        job_name = constants.ROLLBACK_MIGRATIONS_JOB_NAME

    if sub_application_name is not None:
        job_name += '_{}'.format(sub_application_name)
    job = stage.ensure_job(job_name)

    tasks.generate_requirements_install(job, 'configuration')
    tasks.generate_target_directory(job)

    # Fetch the Ansible inventory to use in reaching the EC2 instance.
    if not inventory_location:
        inventory_location = ArtifactLocation(
            pipeline.name,
            deploy_stage.name,
            constants.DEPLOY_AMI_JOB_NAME_TPL(edp),
            constants.DEPLOY_AMI_OUT_FILENAME
        )
    tasks.retrieve_artifact(inventory_location, job)

    # Fetch the SSH key to use in reaching the EC2 instance.
    if not instance_key_location:
        instance_key_location = ArtifactLocation(
            pipeline.name,
            deploy_stage.name,
            constants.DEPLOY_AMI_JOB_NAME_TPL(edp),
            constants.KEY_PEM_FILENAME
        )
    tasks.retrieve_artifact(instance_key_location, job)

    # SSH key used to access the instance needs specific permissions.
    job.ensure_task(tasks.bash_task(
        'chmod 600 {key_pem_path}',
        key_pem_path=path_to_artifact(constants.KEY_PEM_FILENAME)
    ))

    # Fetch the migration output.
    if not migration_info_location:
        migration_info_location = ArtifactLocation(
            pipeline.name,
            deploy_stage.name,
            constants.DEPLOY_AMI_JOB_NAME_TPL(edp),
            constants.MIGRATION_OUTPUT_DIR_NAME,
            is_dir=True
        )
    tasks.retrieve_artifact(migration_info_location, job)

    tasks.generate_migration_rollback(
        job=job,
        application_user=application_user,
        application_name=application_name,
        application_path=application_path,
        db_migration_user=db_migration_user,
        db_migration_pass=db_migration_pass,
        sub_application_name=sub_application_name,
    )

    return job
