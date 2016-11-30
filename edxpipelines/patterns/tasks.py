from gomatic import *

import edxpipelines.constants as constants


def generate_requirements_install(job, working_dir, runif="passed"):
    """
    Generates a command that runs:
    'sudo pip install -r requirements.txt'

    Args:
        job (gomatic.job.Job): the gomatic job which to add install requirements
        working_dir (str): the directory gocd should run the install command from
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """
    return job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                'sudo pip install -r requirements.txt'
            ],
            working_dir=working_dir,
            runif=runif
        )
    )


def generate_launch_instance(job, optional_override_files=[], runif="passed"):
    """
    Generate the launch AMI job. This ansible script generates 3 artifacts:
        key.pem             - Private key material generated for this instance launch
        launch_info.yml     - yaml file that contains information about the instance launched
        ansible_inventory   - a list of private aws IP addresses that can be fed in to ansible to run playbooks

    Args:
        job (gomatic.job.Job): the gomatic job which to add the launch instance task
        runif (str): one of ['passed', 'failed', 'any'] Default: passed
        optional_override_files (list): a list of additional override files to be passed to ansible.
                                        File path should be relative to the root directory the goagent will
                                        execute the job from
                                        The Ansible launch job takes some overrides provided by these files:
                                        https://github.com/edx/configuration/blob/master/playbooks/continuous_delivery/launch_instance.yml

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """
    job.ensure_artifacts(set([BuildArtifact('{}/key.pem'.format(constants.ARTIFACT_PATH)),
                             BuildArtifact('{}/ansible_inventory'.format(constants.ARTIFACT_PATH)),
                             BuildArtifact('{}/launch_info.yml'.format(constants.ARTIFACT_PATH))]))

    command = ' '.join(
        [
            'ansible-playbook ',
            '-vvvv ',
            '--module-path=playbooks/library ',
            '-i "localhost," ',
            '-c local ',
            '-e artifact_path=`/bin/pwd`/../{artifact_path} ',
            '-e base_ami_id=$BASE_AMI_ID ',
            '-e ec2_vpc_subnet_id=$EC2_VPC_SUBNET_ID ',
            '-e ec2_security_group_id=$EC2_SECURITY_GROUP_ID ',
            '-e ec2_instance_type=$EC2_INSTANCE_TYPE ',
            '-e ec2_instance_profile_name=$EC2_INSTANCE_PROFILE_NAME ',
            '-e ebs_volume_size=$EBS_VOLUME_SIZE ',
            '-e hipchat_token=$HIPCHAT_TOKEN ',
            '-e hipchat_room="$HIPCHAT_ROOM" ',
        ]
    )
    command.format(artifact_path=constants.ARTIFACT_PATH)
    for override_file in optional_override_files:
        command += ' -e @../{override_file} '.format(override_file=override_file)
    command += ' playbooks/continuous_delivery/launch_instance.yml'

    return job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                command
            ],
            working_dir=constants.PUBLIC_CONFIGURATION_DIR,
            runif=runif
        )
    )


def generate_create_ami(job, runif="passed", **kwargs):
    """
    TODO: Decouple AMI building and AMI tagging in to 2 different jobs/ansible scripts

    Args:
        job (gomatic.job.Job): the gomatic job which to add the launch instance task
        runif (str): one of ['passed', 'failed', 'any'] Default: passed
        **kwargs (dict):
            k,v pairs:
                k: the name of the option to pass to ansible
                v: the value to use for this option

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """
    job.ensure_artifacts(set([BuildArtifact('{}/ami.yml'.format(constants.ARTIFACT_PATH))]))
    command = ' '.join(
        [
            'ansible-playbook',
            '-vvvv',
            '--module-path=playbooks/library',
            '-i "localhost,"',
            '-c local',
            '-e @../{artifact_path}/launch_info.yml',
            '-e play=$PLAY',
            '-e deployment=$DEPLOYMENT',
            '-e edx_environment=$EDX_ENVIRONMENT',
            '-e app_repo=$APP_REPO',
            '-e configuration_repo=$CONFIGURATION_REPO',
            '-e configuration_version=$GO_REVISION_CONFIGURATION',
            '-e configuration_secure_repo=$CONFIGURATION_SECURE_REPO',
            '-e cache_id=$GO_PIPELINE_COUNTER',
            '-e ec2_region=$EC2_REGION',
            '-e artifact_path=`/bin/pwd`/../{artifact_path}',
            '-e hipchat_token=$HIPCHAT_TOKEN',
            '-e hipchat_room="$HIPCHAT_ROOM"',
            '-e ami_wait=$AMI_WAIT',
            '-e no_reboot=$NO_REBOOT',
            '-e extra_name_identifier=$GO_PIPELINE_COUNTER'
        ]
    )

    command = command.format(artifact_path=constants.ARTIFACT_PATH)
    for k, v in kwargs.iteritems():
        command += ' -e {key}={value} '.format(key=k, value=v)
    command += 'playbooks/continuous_delivery/create_ami.yml'

    return job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                command
            ],
            working_dir=constants.PUBLIC_CONFIGURATION_DIR,
            runif=runif
        )
    )


def generate_ami_cleanup(job, runif="passed"):
    """
    Use in conjunction with patterns.generate_launch_instance this will cleanup the EC2 instances and associated actions

    Args:
        job (gomatic.job.Job): the gomatic job which to add the launch instance task
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """
    return job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                'ansible-playbook '
                '-vvvv '
                '--module-path=playbooks/library '
                '-i "localhost," '
                '-c local '
                '-e @../{artifact_path}/launch_info.yml '
                '-e ec2_region=$EC2_REGION '
                '-e hipchat_token=$HIPCHAT_TOKEN '
                '-e hipchat_room="$HIPCHAT_ROOM" '
                'playbooks/continuous_delivery/cleanup.yml'.format(artifact_path=constants.ARTIFACT_PATH)
            ],
            working_dir=constants.PUBLIC_CONFIGURATION_DIR,
            runif=runif
        )
    )


def generate_run_migrations(job, sub_application_name=None, runif="passed"):
    """
    Generates GoCD task that runs migrations via an Ansible script.

    Assumes:
        - The play will be run using the continuous delivery Ansible config constants.ANSIBLE_CONTINUOUS_DELIVERY_CONFIG

    Args:
        job (gomatic.job.Job): the gomatic job to which the run migrations task will be added
        sub_application_name (str): additional command to be passed to the migrate app {cms|lms}
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """
    job.ensure_artifacts(
        set(
            [BuildArtifact('{}/migrations'.format(constants.ARTIFACT_PATH))]
        )
    )

    command = ' '.join(
        [
            'mkdir -p {artifact_path}/migrations;'
            'export ANSIBLE_HOST_KEY_CHECKING=False;'
            'export ANSIBLE_SSH_ARGS="-o ControlMaster=auto -o ControlPersist=30m";'
            'PRIVATE_KEY=`/bin/pwd`/../{artifact_path}/key.pem;'
            'ansible-playbook '
            '-vvvv '
            '-i ../{artifact_path}/ansible_inventory '
            '--private-key=$PRIVATE_KEY '
            '--module-path=playbooks/library '
            '--user=ubuntu '
            '-e APPLICATION_PATH=$APPLICATION_PATH '
            '-e APPLICATION_NAME=$APPLICATION_NAME '
            '-e APPLICATION_USER=$APPLICATION_USER '
            '-e ARTIFACT_PATH=`/bin/pwd`/../{artifact_path}/migrations '
            '-e DB_MIGRATION_USER=$DB_MIGRATION_USER '
            '-e DB_MIGRATION_PASS=$DB_MIGRATION_PASS '
        ]
    )

    command = command.format(artifact_path=constants.ARTIFACT_PATH)
    if sub_application_name is not None:
        command += '-e SUB_APPLICATION_NAME={sub_application_name} '.format(sub_application_name=sub_application_name)
    command += 'playbooks/continuous_delivery/run_migrations.yml'

    return job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                command
            ],
            working_dir=constants.PUBLIC_CONFIGURATION_DIR,
            runif=runif
        )
    )


def format_RSA_key(job, output_path, key):
    """
    Formats an RSA key for use in future jobs. Does not last between stages.
    Args:
        job (gomatic.job.Job): the gomatic job to which the task will be added
        output_path (str): The file to output the formatted key to.
        key (str): The RSA key to be formatted

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)
    """
    return job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                'touch {output_path} && '
                'chmod 600 {output_path} && '
                'python tubular/scripts/format_rsa_key.py --key "{key}" --output-file {output_path}'.format(
                    output_path=output_path, key=key
                )
            ]
        )
    )


def _fetch_secure_repo(job, secure_dir, secure_repo_envvar, secure_version_envvar, secure_repo_name, runif="passed"):
    """
    Setup a secure repo for use in providing secrets.

    Args:
        job (gomatic.job.Job): the gomatic job to which the task will be added
        secure_dir (str): name of dir containing the edx-ops/configuration-secure repo
        secure_repo_envvar (str): HTTPS-based link to secure repo on GitHub
        secure_version_envvar (str): GitHub ref identifying version of secure repo to use
        secure_repo_name (str): name of secure repo, e.g. "configuration-secure"
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """
    return job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                'touch github_key.pem && '
                'chmod 600 github_key.pem && '
                'python tubular/scripts/format_rsa_key.py --key "$PRIVATE_GITHUB_KEY" --output-file github_key.pem && '
                "GIT_SSH_COMMAND='/usr/bin/ssh -o StrictHostKeyChecking=no -i github_key.pem' "
                '/usr/bin/git clone ${secure_repo_envvar} {secure_dir} && '
                'cd {secure_dir} && '
                '/usr/bin/git checkout ${secure_version_envvar} && '
                '[ -d ../{artifact_path}/ ] && echo "Target Directory Exists" || mkdir ../{artifact_path}/ && '
                '/usr/bin/git rev-parse HEAD > ../{artifact_path}/{secure_repo_name}_sha'.format(
                    secure_dir=secure_dir,
                    secure_repo_envvar=secure_repo_envvar,
                    secure_version_envvar=secure_version_envvar,
                    secure_repo_name=secure_repo_name,
                    artifact_path=constants.ARTIFACT_PATH
                )
            ]
        )
    )


def generate_target_directory(job, directory_name=constants.ARTIFACT_PATH, runif="passed"):
    return job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c ',
                '[ -d {0} ] && echo "Directory Exists" || mkdir {0} '.format(directory_name)
            ],
            runif=runif
        )
    )


def fetch_secure_configuration(job, secure_dir, runif="passed"):
    """
    Setup the configuration-secure repo for use in providing secrets.

    Stage using this task must have the following environment variables:
        CONFIGURATION_SECURE_REPO
        CONFIGURATION_SECURE_VERSION

    Args:
        job (gomatic.job.Job): the gomatic job to which the playbook run task will be added
        secure_dir (str): name of dir containing the edx-ops/configuration-secure repo
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """
    return _fetch_secure_repo(
        job, secure_dir,
        "CONFIGURATION_SECURE_REPO",
        "CONFIGURATION_SECURE_VERSION",
        "configuration-secure"
    )


def fetch_gomatic_secure(job, secure_dir, runif="passed"):
    """
    Setup the gomatic-secure repo for use in providing secrets.

    Stage using this task must have the following environment variables:
        GOMATIC_SECURE_REPO
        GOMATIC_SECURE_VERSION
        PRIVATE_GITHUB_KEY

    Args:
        job (gomatic.job.Job): the gomatic job to which the task will be added
        secure_dir (str): name of dir containing the edx-ops/gomatic-secure repo
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """
    return _fetch_secure_repo(
        job, secure_dir,
        "GOMATIC_SECURE_REPO",
        "GOMATIC_SECURE_VERSION",
        "gomatic-secure"
    )


def fetch_edx_mktg(job, secure_dir, runif="passed"):
    """
    Setup the edx-mktg repo for use with Drupal deployment.

    Stage using this task must have the following environment variables:
        PRIVATE_MARKETING_REPOSITORY_URL
        MARKETING_REPOSITORY_VERSION

    Args:
        job (gomatic.job.Job): the gomatic job to which the task will be added
        secure_dir (str): name of dir containing the edx/edx-mktg repo
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)
    """
    return _fetch_secure_repo(
        job, secure_dir,
        "PRIVATE_MARKETING_REPOSITORY_URL",
        "MARKETING_REPOSITORY_VERSION",
        "edx-mktg"
    )


def generate_run_app_playbook(job, internal_dir, secure_dir, playbook_path, runif="passed", **kwargs):
    """
    Generates:
        a GoCD task that runs an Ansible playbook against a server inventory.

    Assumes:
        - The play will be run using the continuous delivery ansible config constants.ANSIBLE_CONTINUOUS_DELIVERY_CONFIG
        - The play will be run from the constants.PUBLIC_CONFIGURATION_DIR directory
        - a key file for this host in "{constants.ARTIFACT_PATH}/key.pem"
        - a ansible inventory file "{constants.ARTIFACT_PATH}/ansible_inventory"
        - a launch info file "{constants.ARTIFACT_PATH}/launch_info.yml"

    The calling pipline for this task must have the following materials:
        - edx-secure
        - configuration

        These are generated by edxpipelines.patterns.stages.generate_launch_instance

    Args:
        job (gomatic.job.Job): the gomatic job to which the playbook run task will be added
        secure_dir (str): name of dir containing the edx-ops/configuration-secure repo
        playbook_path (str): path to playbook relative to the top-level 'configuration' directory
        runif (str): one of ['passed', 'failed', 'any'] Default: passed
        **kwargs (dict):
            k,v pairs:
                k: the name of the option to pass to ansible
                v: the value to use for this option

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """
    command = ' '.join(
        [
            'chmod 600 ../{artifact_path}/key.pem;',
            'export ANSIBLE_HOST_KEY_CHECKING=False;',
            'export ANSIBLE_SSH_ARGS="-o ControlMaster=auto -o ControlPersist=30m";',
            'PRIVATE_KEY=$(/bin/pwd)/../{artifact_path}/key.pem;'
            'ansible-playbook',
            '-vvvv',
            '--private-key=$PRIVATE_KEY',
            '--user=ubuntu',
            '--module-path=playbooks/library ',
            '-i ../{artifact_path}/ansible_inventory '
            '-e @../{artifact_path}/launch_info.yml',
            '-e @../{internal_dir}/ansible/vars/${{DEPLOYMENT}}.yml',
            '-e @../{internal_dir}/ansible/vars/${{EDX_ENVIRONMENT}}-${{DEPLOYMENT}}.yml',
            '-e @../{secure_dir}/ansible/vars/${{DEPLOYMENT}}.yml',
            '-e @../{secure_dir}/ansible/vars/${{EDX_ENVIRONMENT}}-${{DEPLOYMENT}}.yml',
        ]
    )
    command = command.format(secure_dir=secure_dir, internal_dir=internal_dir, artifact_path=constants.ARTIFACT_PATH)
    for k, v in kwargs.iteritems():
        command += ' -e {key}={value} '.format(key=k, value=v)
    command += playbook_path

    return job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                command
            ],
            working_dir=constants.PUBLIC_CONFIGURATION_DIR,
            runif=runif
        )
    )


def generate_backup_drupal_database(job, site_env):
    """
    Creates a backup of the database in the given environment.

    Stage using this task must have the following environment variables:
        PRIVATE_ACQUIA_USERNAME
        PRIVATE_ACQUIA_PASSWORD

    Args:
        job (gomatic.job.Job): the gomatic job to which the task will be added
        site_env (str): The environment to clear caches from. Choose 'test' for stage and 'prod' for prod

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)
    """
    return job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                'python scripts/drupal_backup_database.py '
                '--env {site_env} '
                '--username $PRIVATE_ACQUIA_USERNAME '
                '--password $PRIVATE_ACQUIA_PASSWORD'.format(site_env=site_env)
            ],
            working_dir='tubular'
        )
    )


def generate_flush_drupal_caches(job, site_env):
    """
    Flushes all drupal caches
    Assumes the drupal root is located in edx-mktg/docroot. If changed, change the working dir.

    Args:
        job (gomatic.job.Job): the gomatic job to which the task will be added
        site_env (str): The environment to clear caches from. Choose 'test' for stage and 'prod' for prod

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)
    """
    return job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                'drush -y @edx.{site_env} cc all'.format(site_env=site_env)
            ],
            working_dir='edx-mktg/docroot'
        )
    )


def generate_clear_varnish_cache(job, site_env):
    """
    Clears the Varnish cache in the given environment.

    Stage using this task must have the following environment variables:
        PRIVATE_ACQUIA_USERNAME
        PRIVATE_ACQUIA_PASSWORD

    Args:
        job (gomatic.job.Job): the gomatic job to which the task will be added
        site_env (str): The environment to clear caches from. Choose 'test' for stage and 'prod' for prod

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)
    """
    return job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                'python scripts/drupal_clear_varnish.py '
                '--env {site_env} '
                '--username $PRIVATE_ACQUIA_USERNAME '
                '--password $PRIVATE_ACQUIA_PASSWORD'.format(site_env=site_env)
            ],
            working_dir='tubular'
        )
    )


def generate_drupal_deploy(job, site_env, tag_file):
    """
    Deploys the given tag to the environment.

    Stage using this task must have the following environment variables:
        PRIVATE_ACQUIA_USERNAME
        PRIVATE_ACQUIA_PASSWORD

    Expects there to be:
        - a text file containing the tag name in "{constants.ARTIFACT_PATH}/tag_file"

    Args:
        job (gomatic.job.Job): the gomatic job to which the task will be added
        site_env (str): The environment to clear caches from. Choose 'test' for stage and 'prod' for prod
        tag_file (str): The name of the file containing the name of the tag to deploy.

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)
    """
    return job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                'python scripts/drupal_deploy.py '
                '--env {site_env} '
                '--username $PRIVATE_ACQUIA_USERNAME '
                '--password $PRIVATE_ACQUIA_PASSWORD '
                '--tag $(cat ../{artifact_path}/{tag_file})'.format(site_env=site_env,
                                                                    tag_file=tag_file,
                                                                    artifact_path=constants.ARTIFACT_PATH)
            ],
            working_dir='tubular'
        )
    )


def generate_fetch_tag(job, site_env, path_name):
    """
    Fetches the name of the current tag deployed in the environment.

    Stage using this task must have the following environment variables:
        PRIVATE_ACQUIA_USERNAME
        PRIVATE_ACQUIA_PASSWORD

    Args:
        job (gomatic.job.Job): the gomatic job to which the task will be added
        site_env (str): The environment to clear caches from. Choose 'test' for stage and 'prod' for prod
        path_name (str): The path to write the tag names to.

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)
    """
    return job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                'python scripts/drupal_fetch_deployed_tag.py '
                '--env {site_env} '
                '--username $PRIVATE_ACQUIA_USERNAME '
                '--password $PRIVATE_ACQUIA_PASSWORD '
                '--path_name {path_name}'.format(site_env=site_env, path_name=path_name)
            ],
            working_dir='tubular'
        )
    )


def generate_refresh_metadata(job, runif='passed'):
    """
    Generates GoCD task that refreshes metadata (for the Catalog Service) via an Ansible script.

    Args:
        job (gomatic.job.Job): the gomatic job to which the run migrations task will be added
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """
    command = ' '.join(
        [
            'export ANSIBLE_HOST_KEY_CHECKING=False;'
            'export ANSIBLE_SSH_ARGS="-o ControlMaster=auto -o ControlPersist=30m";'
            'PRIVATE_KEY=`/bin/pwd`/../../key.pem;'
            'ansible-playbook '
            '-vvvv '
            '-i ../../ansible_inventory '
            '--private-key=$PRIVATE_KEY '
            '--user=ubuntu '
            '-e APPLICATION_PATH=$APPLICATION_PATH '
            '-e APPLICATION_NAME=$APPLICATION_NAME '
            '-e APPLICATION_USER=$APPLICATION_USER '
            '-e HIPCHAT_TOKEN=$HIPCHAT_TOKEN '
            '-e HIPCHAT_ROOM="$HIPCHAT_ROOM" '
            'discovery_refresh_metadata.yml '
        ]
    )

    return job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                command
            ],
            working_dir='configuration/playbooks/continuous_delivery/',
            runif=runif
        )
    )


def generate_update_index(job, runif='passed'):
    """
    Generates GoCD task that runs the Haystack update_index management command via an Ansible script.

    Args:
        job (gomatic.job.Job): the gomatic job to which the run migrations task will be added
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """
    command = ' '.join(
        [
            'export ANSIBLE_HOST_KEY_CHECKING=False;'
            'export ANSIBLE_SSH_ARGS="-o ControlMaster=auto -o ControlPersist=30m";'
            'PRIVATE_KEY=`/bin/pwd`/../../key.pem;'
            'ansible-playbook '
            '-vvvv '
            '-i ../../ansible_inventory '
            '--private-key=$PRIVATE_KEY '
            '--user=ubuntu '
            '-e APPLICATION_PATH=$APPLICATION_PATH '
            '-e APPLICATION_NAME=$APPLICATION_NAME '
            '-e APPLICATION_USER=$APPLICATION_USER '
            '-e HIPCHAT_TOKEN=$HIPCHAT_TOKEN '
            '-e HIPCHAT_ROOM="$HIPCHAT_ROOM" '
            'haystack_update_index.yml '
        ]
    )

    return job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                command
            ],
            working_dir='configuration/playbooks/continuous_delivery/',
            runif=runif
        )
    )
