from gomatic import *

import edxpipelines.constants as constants
import edxpipelines.patterns.tasks as tasks


def generate_rollback_migration(stage,
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
    job.add_task(inventory_location.as_fetch_task(constants.ARTIFACT_PATH))

    # Fetch the SSH key to use in reaching the EC2 instance.
    job.add_task(instance_key_location.as_fetch_task(constants.ARTIFACT_PATH))

    # fetch the migration outputs
    job.add_task(migration_info_location.as_fetch_task(constants.ARTIFACT_PATH))

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
