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

from gomatic import ExecTask

import edxpipelines.constants as constants
import edxpipelines.patterns.tasks as tasks


def generate_build_ami(pipeline,
                       stage,
                       edp,
                       app_repo_url,
                       config_secure_repo_url,
                       playbook_path,
                       env_config,
                       **kwargs):
    """
    Generates a job for creating a new AMI.

    Args:
        pipeline (gomatic.gocd.pipelines.Pipeline): Pipeline to which this job belongs.
        stage (gomatic.gocd.pipelines.Stage): Stage to which this job belongs.
        edp (edxpipelines.utils.EDP): Tuple indicating environment, deployment, and play
            for which an AMI will be created.
        app_repo_url (str): App repo's URL.
        config_secure_repo_url (str): Secure configuration repo's URL.
        playbook_path (str): Path to the Ansible playbook to run when creating the AMI.
        env_config (dict): Environment-specific secure config.

    Returns:
        gomatic.gocd.pipelines.Job
    """
    job_name = '{environment}_{base_job_name}'.format(
        environment=edp.environment,
        base_job_name=constants.BUILD_AMI_JOB_NAME
    )
    job = stage.ensure_job(job_name)

    tasks.generate_requirements_install(job, 'configuration')
    tasks.generate_package_install(job, 'tubular')
    tasks.generate_target_directory(job)

    # Locate the base AMI.
    tasks.generate_base_ami_selection(
        pipeline,
        job,
        env_config['aws_access_key_id'],
        env_config['aws_secret_access_key'],
        edx_environment=edp.environment,
        deployment=edp.deployment,
        play=edp.play,
        base_ami_id=env_config['base_ami_id'],
    )

    # Launch a new instance on which to build the AMI.
    tasks.generate_launch_instance(
        pipeline,
        job,
        aws_access_key_id=env_config['aws_access_key_id'],
        aws_secret_access_key=env_config['aws_secret_access_key'],
        ec2_vpc_subnet_id=env_config['ec2_vpc_subnet_id'],
        ec2_security_group_id=env_config['ec2_security_group_id'],
        ec2_instance_profile_name=env_config['ec2_instance_profile_name'],
        base_ami_id=env_config['base_ami_id'],
        variable_override_path='{}/{}'.format(
            constants.ARTIFACT_PATH,
            constants.BASE_AMI_OVERRIDE_FILENAME,
        ),
    )

    # Run the Ansible play for the service.
    tasks.generate_run_app_playbook(
        pipeline,
        job,
        playbook_path,
        edp,
        app_repo_url,
        private_github_key=env_config['github_private_key'],
        hipchat_token=env_config['hipchat_token'],
        disable_edx_services='true',
        COMMON_TAG_EC2_INSTANCE='true',
        **kwargs
    )

    # Create an AMI from the instance.
    tasks.generate_create_ami(
        pipeline,
        job,
        edp.play,
        edp.deployment,
        edp.environment,
        app_repo_url,
        config_secure_repo_url,
        env_config['aws_access_key_id'],
        env_config['aws_secret_access_key'],
        launch_info_path='{}/{}'.format(
            constants.ARTIFACT_PATH,
            constants.LAUNCH_INSTANCE_FILENAME,
        ),
        configuration_secure_version='$GO_REVISION_CONFIGURATION_SECURE',
        hipchat_token=env_config['hipchat_token'],
        **kwargs
    )

    tasks.generate_ami_cleanup(job, runif='any')

    return job


def generate_rollback_migration(
        stage,
        inventory_location,
        instance_key_location,
        migration_info_location,
        sub_application_name=None
):
    """

    Args:
        stage (gomatic.gocd.pipelines.Stage): Stage this job will be part of
        inventory_location (utils.ArtifactLocation): Location of the ansible inventory location
        instance_key_location (utils.ArtifactLocation): Location of key used to ssh in to the instance
        migration_info_location (utils.ArtifactLocation): Location of the migration output to roll back
        sub_application_name (str): additional command to be passed to the migrate app {cms|lms}

    Returns:
        gomatic.gocd.pipelines.Job

    """
    job_name = constants.ROLLBACK_MIGRATIONS_JOB_NAME
    if sub_application_name is not None:
        job_name += "_{}".format(sub_application_name)
    job = stage.ensure_job(job_name)

    # Fetch the Ansible inventory to use in reaching the EC2 instance.
    tasks.retrieve_artifact(inventory_location, job, constants.ARTIFACT_PATH)

    # Fetch the SSH key to use in reaching the EC2 instance.
    tasks.retrieve_artifact(instance_key_location, job, constants.ARTIFACT_PATH)

    # fetch the migration outputs
    tasks.retrieve_artifact(migration_info_location, job, constants.ARTIFACT_PATH)

    # ensure the target directoy exists
    tasks.generate_target_directory(job)

    # The SSH key used to access the EC2 instance needs specific permissions.
    job.add_task(
        ExecTask(
            ['/bin/bash', '-c', 'chmod 600 {}'.format(instance_key_location.file_name)],
            working_dir=constants.ARTIFACT_PATH
        )
    )

    tasks.generate_requirements_install(job, 'configuration')
    tasks.generate_migration_rollback(job, sub_application_name)

    return job
