from gomatic import *


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


def generate_launch_instance(job, runif="passed"):
    """
    Generate the launch AMI job. This ansible script generates 3 artifacts:
        key.pem             - Private key material generated for this instance launch
        launch_info.yml     - yaml file that contains information about the instance launched
        ansible_inventory   - a list of private aws IP addresses that can be fed in to ansible to run playbooks

    Args:
        job (gomatic.job.Job): the gomatic job which to add the launch instance task
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """
    job.ensure_artifacts(set([BuildArtifact("target/key.pem"),
                             BuildArtifact("target/ansible_inventory"),
                             BuildArtifact("target/launch_info.yml")]))
    return job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                'ansible-playbook '
                '-vvvv '
                '--module-path=../library '
                '-i "localhost," '
                '-c local '
                '-e artifact_path=`/bin/pwd`/../../../$ARTIFACT_PATH '
                '-e base_ami_id=$BASE_AMI_ID '
                '-e ec2_vpc_subnet_id=$EC2_VPC_SUBNET_ID '
                '-e ec2_security_group_id=$EC2_SECURITY_GROUP_ID '
                '-e ec2_instance_type=$EC2_INSTANCE_TYPE '
                '-e ec2_instance_profile_name=$EC2_INSTANCE_PROFILE_NAME '
                '-e ebs_volume_size=$EBS_VOLUME_SIZE '
                'launch_instance.yml'
            ],
            working_dir="configuration/playbooks/continuous_delivery/",
            runif=runif
        )
    )


def generate_create_edxapp_ami(job, runif="passed"):
    """
    TODO: Decouple AMI building and AMI tagging in to 2 different jobs/ansible scripts

    Args:
        job (gomatic.job.Job): the gomatic job which to add the launch instance task
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """
    job.ensure_artifacts(set([BuildArtifact("target/ami.yml")]))
    return job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                'ansible-playbook '
                '-vvvv '
                '--module-path=../library '
                '-i "localhost," '
                '-c local '
                '-e @../../../target/launch_info.yml '
                '-e play=$PLAY '
                '-e deployment=$DEPLOYMENT '
                '-e edx_environment=$EDX_ENVIRONMENT '
                '-e app_repo=$APP_REPO '
                '-e app_version=$APP_VERSION '
                '-e configuration_repo=$CONFIGURATION_REPO '
                '-e configuration_version=$CONFIGURATION_VERSION '
                '-e configuration_secure_repo=$CONFIGURATION_SECURE_REPO '
                '-e configuration_secure_version=$CONFIGURATION_SECURE_VERSION '
                '-e cache_id=$CACHE_ID '
                '-e ec2_region=$EC2_REGION '
                '-e artifact_path=`/bin/pwd`/../../../$ARTIFACT_PATH '
                '-e edx_app_theme_repo=$EDX_APP_THEME_REPO '
                '-e edx_app_theme_version=$EDX_APP_THEME_VERSION '
                '-e hipchat_token=$HIPCHAT_TOKEN '
                '-e hipchat_room="$HIPCHAT_ROOM" '
                '-e ami_wait=$AMI_WAIT '
                '-e no_reboot=$NO_REBOOT '
                'create_ami.yml'
            ],
            working_dir="configuration/playbooks/continuous_delivery/",
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
    job.ensure_artifacts(set([BuildArtifact("target/ami.yml")]))
    command = ' '.join(
        [
            'ansible-playbook',
            '-vvvv',
            '--module-path=../library',
            '-i "localhost,"',
            '-c local',
            '-e @../../../target/launch_info.yml',
            '-e play=$PLAY',
            '-e deployment=$DEPLOYMENT',
            '-e edx_environment=$EDX_ENVIRONMENT',
            '-e app_repo=$APP_REPO',
            '-e app_version=$APP_VERSION',
            '-e configuration_repo=$CONFIGURATION_REPO',
            '-e configuration_version=$CONFIGURATION_VERSION',
            '-e configuration_secure_repo=$CONFIGURATION_SECURE_REPO',
            '-e configuration_secure_version=$CONFIGURATION_SECURE_VERSION',
            '-e cache_id=$CACHE_ID',
            '-e ec2_region=$EC2_REGION',
            '-e artifact_path=`/bin/pwd`/../../../$ARTIFACT_PATH',
            '-e hipchat_token=$HIPCHAT_TOKEN',
            '-e hipchat_room="$HIPCHAT_ROOM"',
            '-e ami_wait=$AMI_WAIT',
            '-e no_reboot=$NO_REBOOT'
        ]
    )

    for k, v in kwargs.iteritems():
        command += ' -e {key}={value} '.format(key=k, value=v)
    command += 'create_ami.yml'

    return job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                command
            ],
            working_dir="configuration/playbooks/continuous_delivery/",
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
                '--module-path=../library '
                '-i "localhost," '
                '-c local '
                '-e @../../../target/launch_info.yml '
                '-e ec2_region=$EC2_REGION '
                '-e hipchat_token=$HIPCHAT_TOKEN '
                '-e hipchat_room="$HIPCHAT_ROOM" '
                'cleanup.yml'
            ],
            working_dir="configuration/playbooks/continuous_delivery/",
            runif=runif
        )
    )


def generate_run_migrations(job, runif="passed"):
    """
    Generates GoCD task that runs migrations via an Ansible script.

    Args:
        job (gomatic.job.Job): the gomatic job to which the run migrations task will be added
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """
    job.ensure_artifacts(set([BuildArtifact('target/unapplied_migrations.yml'),
                              BuildArtifact('target/migration_output.yml')]))
    return job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
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
                '-e ARTIFACT_PATH=`/bin/pwd`/../../../$ARTIFACT_PATH/ '
                '-e DB_MIGRATION_USER=$DB_MIGRATION_USER '
                '-e DB_MIGRATION_PASS=$DB_MIGRATION_PASS '
                'run_migrations.yml'
            ],
            working_dir='configuration/playbooks/continuous_delivery/',
            runif=runif
        )
    )


def guarantee_configuration_version(job, runif="passed"):
    """
    Check out the configuration version specified in $CONFIGURATION_VERSION.
    This is a work around to add the ability to checkout a specific git sha, which GoCD does not support.

    Args:
        job (gomatic.job.Job): the gomatic job to which the playbook run task will be added
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """
    return job.add_task(
        ExecTask(
            [
                '/bin/bash',
                '-c',
                '/usr/bin/git fetch && '
                '/usr/bin/git pull && '
                '/usr/bin/git checkout $CONFIGURATION_VERSION'
            ],
            working_dir='configuration/'
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
                'mkdir ../target/ && '
                '/usr/bin/git rev-parse HEAD > ../target/{secure_repo_name}_sha'.format(
                    secure_dir=secure_dir,
                    secure_repo_envvar=secure_repo_envvar,
                    secure_version_envvar=secure_version_envvar,
                    secure_repo_name=secure_repo_name
                )
            ]
        )
    )


def generate_target_directory(job, directory_name="target", runif="passed"):
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


def generate_run_app_playbook(job, secure_dir, playbook_path, runif="passed", **kwargs):
    """
    Generates a GoCD task that runs an Ansible playbook against a server inventory.
    Expects there to be:
        - a key file for this host in "${{ARTIFACT_PATH}}/key.pem"
        - a ansible inventory file "${{ARTIFACT_PATH}}/ansible_inventory"
        - a launch info file "${{ARTIFACT_PATH}}/launch_info.yml"

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
            'chmod 600 ../${{ARTIFACT_PATH}}/key.pem;',
            'export ANSIBLE_HOST_KEY_CHECKING=False;',
            'export ANSIBLE_SSH_ARGS="-o ControlMaster=auto -o ControlPersist=30m";',
            'PRIVATE_KEY=`/bin/pwd`/../${{ARTIFACT_PATH}}/key.pem;',
            'ansible-playbook',
            '-vvvv',
            '--private-key=$PRIVATE_KEY',
            '--user=ubuntu',
            '--module-path=configuration/playbooks/library ',
            '-i ../target/ansible_inventory',
            '-e @../target/launch_info.yml',
            '-e @../{secure_dir}/ansible/vars/${{DEPLOYMENT}}.yml',
            '-e @../{secure_dir}/ansible/vars/${{EDX_ENVIRONMENT}}-${{DEPLOYMENT}}.yml',
            '-e cache_id=$GO_PIPELINE_COUNTER'
        ]
    )
    command = command.format(secure_dir=secure_dir)
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
            working_dir='configuration',
            runif=runif
        )
    )
