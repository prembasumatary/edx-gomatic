"""
Common gomatic task patterns.

Responsibilities:
    Task patterns should ...
        * ``ensure`` the environment variables that they need to use.
            * This hides the implementation of how values are being passed to scripts from callers.
        * use ``ensure_task`` if the task only needs to be run once.
        * expect file paths as input (and produce files at well-documented paths).
            * Because you can't fetch an artifact from a stage that's in progress, tasks
              should assume that artifacts that they need will already have been fetched
              by one of the higher-up constructs.
        * return the generated task (if there was only one), or a list of tasks, if there are multiple
          (or, for extra credit, a namedtuple, so that the tasks can be named).
        * use constants for all folder/filenames that are known in advance (rather than
          being arguments to the pattern).
        * ``ensure`` the scm materials needed for the task to function.
"""
import re
import textwrap

from gomatic import ExecTask, BuildArtifact, FetchArtifactFile, FetchArtifactDir, FetchArtifactTask


from edxpipelines import constants


def ansible_task(
        variables, playbook, runif='passed',
        working_dir=constants.PUBLIC_CONFIGURATION_DIR,
        inventory=None, prefix=None, extra_options=None,
        verbosity=3,
):
    """
    Run ansible-playbook.

    Arguments:
        variables (list of pairs or strings):
            Variable overrides to pass to ansible on the commandline. Strings will be
            interpreted as paths to files containing variable overrides.
        playbook (str): The path (from the working_dir) to the playbook to execute.
        runif (str): One of 'passed', 'failed', or 'any'. Specifies whether to run this task.
        working_dir (str): The directory to start ansible from.
        inventory (str): The inventory file to run with. If None, ansible will be run in local mode.
        prefix (list): A list of bash snippets that should be pre-pended to the ansible execution.
            These will be joined with whitespace.
        extra_options (list): A list of bash snippets that will be appended to the ansible command
            (before variables). These will be joined with whitespace.
        verbosity (int): How many ``-v`` parameters to add when running ansible

    Returns: An ExecTask that executes the ansible play.
    """
    if prefix is None:
        prefix = []

    if extra_options is None:
        extra_options = []

    if inventory is None:
        inventory = [
            '-i', '"localhost,"',
            '-c', 'local',
        ]
    else:
        inventory = [
            "-i", inventory
        ]

    command = prefix + [
        'ansible-playbook',
    ]
    if verbosity > 0:
        command.append('-' + 'v' * verbosity)

    command.extend(inventory)
    command.extend(extra_options)

    for variable in variables:
        if isinstance(variable, basestring):
            command.append(' -e @../{} '.format(variable))
        else:
            name, value = variable
            command.append('-e {}={}'.format(name, value))

    command.append(playbook)

    return ExecTask(
        [
            '/bin/bash',
            '-c',
            ' '.join(command)
        ],
        working_dir=working_dir,
        runif=runif
    )


def tubular_task(script, arguments, prefix=None, runif='passed', working_dir='tubular'):
    """
    Execute a tubular script in a standard way.

    Arguments:
        script (str): The name of the script inside tubular/script.
        arguments (list): A list of bash snippets to append as arguments to the script name.
            Will be whitespace-separated.
        prefix (list): A list of bash snippets to prepend to script execution. Will be
            whitespace-separated.
        runif (str): One of 'passed', 'failed', or 'any'. Specifies whether to run this task.

    Returns: An ExecTask that runs a tubular script.
    """
    if prefix is None:
        prefix = []

    command = prefix + [script] + arguments

    return ExecTask(
        [
            '/bin/bash',
            '-c',
            ' '.join(command)
        ],
        working_dir=working_dir,
        runif=runif
    )


def bash_task(script, working_dir=None, runif="passed", **kwargs):
    '''
    Execute a bash script in a standard way.

    For example:

    bash_task(
        """\\
            echo {message} &&
            echo {message}
        """,
        message="'Help!'"
    )

    will cause the bash script "echo 'Help!' && echo 'Help!'" to run.

    Arguments:
        script: The script to execute. First, any **kwargs will be formatted
            in to the script. Second, textwrap.dedent will be used to normalize
            indentation. Third, any newlines with trailing spaces will be replaced
            by single spaces.
        working_dir (str): The directory to run the script in.
        runif (str): One of 'passed', 'failed', or 'any'. Specifies whether to run this task.
        **kwargs: Values to substitute into ``script``.
    '''
    return ExecTask(
        [
            '/bin/bash',
            '-c',
            re.sub(
                r"$\s+",
                " ",
                textwrap.dedent(script.format(**kwargs)),
                flags=re.MULTILINE
            ).strip(),
        ],
        working_dir=working_dir,
        runif=runif
    )


def retrieve_artifact(artifact_location, job, dest=constants.ARTIFACT_PATH, runif="passed"):
    """
    Make sure that there is a task in ``job`` that will retrieve ``ArtifactLocation`` to the folder ``dest``.
    Also ensures that ``dest`` has been created.
    """
    generate_target_directory(job, dest, runif=runif)
    if artifact_location.is_dir:
        src = FetchArtifactDir(artifact_location.file_name)
    else:
        src = FetchArtifactFile(artifact_location.file_name)  # pylint: disable=redefined-variable-type

    job.ensure_task(FetchArtifactTask(
        pipeline=artifact_location.pipeline,
        stage=artifact_location.stage,
        job=artifact_location.job,
        src=src,
        dest=dest
    ))


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
    return job.add_task(bash_task(
        'sudo pip install -r requirements.txt',
        working_dir=working_dir,
        runif=runif
    ))


def generate_package_install(job, working_dir, runif="passed", pip="pip3"):
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
    return job.add_task(bash_task(
        'sudo {} install --upgrade .'.format(pip),
        working_dir=working_dir,
        runif=runif,
    ))


def generate_launch_instance(
        pipeline, job, aws_access_key_id, aws_secret_access_key,
        ec2_vpc_subnet_id, ec2_security_group_id, ec2_instance_profile_name,
        base_ami_id, ec2_region=constants.EC2_REGION, ec2_instance_type=constants.EC2_INSTANCE_TYPE,
        ec2_timeout=constants.EC2_LAUNCH_INSTANCE_TIMEOUT,
        ec2_ebs_volume_size=constants.EC2_EBS_VOLUME_SIZE,
        variable_override_path=None, runif="passed"
):
    """
    Generate the launch AMI job. This ansible script generates 3 artifacts:
        key.pem             - Private key material generated for this instance launch
        launch_info.yml     - yaml file that contains information about the instance launched
        ansible_inventory   - a list of private aws IP addresses that can be fed in to ansible to run playbooks

    Args:
        job (gomatic.job.Job): the gomatic job which to add the launch instance task
        runif (str): one of ['passed', 'failed', 'any'] Default: passed
        variable_override_path (str): The path to an already-retrieved yaml file specifying
            variable overrides to use when launching the instance.

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

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

    # fetch the artifacts if there are any
    optional_override_files = []
    if variable_override_path:
        optional_override_files.append(variable_override_path)

    job.ensure_artifacts({
        BuildArtifact('{}/key.pem'.format(constants.ARTIFACT_PATH)),
        BuildArtifact('{}/ansible_inventory'.format(constants.ARTIFACT_PATH)),
        BuildArtifact('{}/launch_info.yml'.format(constants.ARTIFACT_PATH))
    })

    return job.add_task(ansible_task(
        variables=[
            ('artifact_path', '`/bin/pwd`/../{} '.format(constants.ARTIFACT_PATH)),
            ('base_ami_id', '$BASE_AMI_ID'),
            ('ec2_vpc_subnet_id', '$EC2_VPC_SUBNET_ID'),
            ('ec2_security_group_id', '$EC2_SECURITY_GROUP_ID'),
            ('ec2_instance_type', '$EC2_INSTANCE_TYPE'),
            ('ec2_instance_profile_name', '$EC2_INSTANCE_PROFILE_NAME'),
            ('ebs_volume_size', '$EBS_VOLUME_SIZE'),
            ('hipchat_token', '$HIPCHAT_TOKEN'),
            ('hipchat_room', '"$HIPCHAT_ROOM"'),
            ('ec2_timeout', '900'),
        ] + optional_override_files,
        extra_options=['--module-path=playbooks/library'],
        playbook='playbooks/continuous_delivery/launch_instance.yml',
        runif=runif,
    ))


def generate_create_ami(
        pipeline, job, play, deployment, edx_environment,
        app_repo, configuration_secure_repo, aws_access_key_id,
        aws_secret_access_key, launch_info_path,
        configuration_repo=constants.PUBLIC_CONFIGURATION_REPO_URL,
        ami_creation_timeout='3600', ami_wait='yes', cache_id='',
        artifact_path=constants.ARTIFACT_PATH, hipchat_token='',
        hipchat_room=constants.HIPCHAT_ROOM,
        runif='passed', **kwargs
):
    """
    TODO: Decouple AMI building and AMI tagging in to 2 different jobs/ansible scripts

    Args:
        job (gomatic.job.Job): the gomatic job which to add the launch instance task
        runif (str): one of ['passed', 'failed', 'any'] Default: passed
        launch_info_path (str): The path to launch_info.yml
        **kwargs (dict):
            k,v pairs:
                k: the name of the option to pass to ansible
                v: the value to use for this option

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """
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

    job.ensure_artifacts(set([BuildArtifact('{}/ami.yml'.format(constants.ARTIFACT_PATH))]))
    variables = [
        launch_info_path,
        ('play', '$PLAY'),
        ('deployment', '$DEPLOYMENT'),
        ('edx_environment', '$EDX_ENVIRONMENT'),
        ('app_repo', '$APP_REPO'),
        ('configuration_repo', '$CONFIGURATION_REPO'),
        ('configuration_version', '$GO_REVISION_CONFIGURATION'),
        ('configuration_secure_repo', '$CONFIGURATION_SECURE_REPO'),
        ('cache_id', '$GO_PIPELINE_COUNTER'),
        ('ec2_region', '$EC2_REGION'),
        ('artifact_path', '`/bin/pwd`/../{}'.format(constants.ARTIFACT_PATH)),
        ('hipchat_token', '$HIPCHAT_TOKEN'),
        ('hipchat_room', '"$HIPCHAT_ROOM"'),
        ('ami_wait', '$AMI_WAIT'),
        ('no_reboot', '$NO_REBOOT'),
        ('extra_name_identifier', '$GO_PIPELINE_COUNTER'),
    ]
    variables.extend(sorted(kwargs.items()))

    return job.add_task(ansible_task(
        variables=variables,
        extra_options=['--module-path=playbooks/library'],
        playbook='playbooks/continuous_delivery/create_ami.yml',
        runif=runif
    ))


def generate_ami_cleanup(job, runif="passed"):
    """
    Use in conjunction with patterns.generate_launch_instance this will cleanup the EC2 instances and associated actions

    Args:
        job (gomatic.job.Job): the gomatic job which to add the launch instance task
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """
    return job.add_task(ansible_task(
        variables=[
            '{}/launch_info.yml'.format(constants.ARTIFACT_PATH),
            ('ec2_region', '$EC2_REGION'),
            ('hipchat_token', '$HIPCHAT_TOKEN'),
            ('hipchat_room', '"$HIPCHAT_ROOM"'),
        ],
        extra_options=['--module-path=playbooks/library'],
        playbook='playbooks/continuous_delivery/cleanup.yml',
        runif=runif,
    ))


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

    variables = [
        ('APPLICATION_PATH', '$APPLICATION_PATH'),
        ('APPLICATION_NAME', '$APPLICATION_NAME'),
        ('APPLICATION_USER', '$APPLICATION_USER'),
        ('ARTIFACT_PATH', '`/bin/pwd`/../{}/migrations'.format(constants.ARTIFACT_PATH)),
        ('DB_MIGRATION_USER', '$DB_MIGRATION_USER'),
        ('DB_MIGRATION_PASS', '$DB_MIGRATION_PASS'),
    ]

    if sub_application_name is not None:
        variables.append(('SUB_APPLICATION_NAME', sub_application_name))

    return job.add_task(ansible_task(
        prefix=[
            'mkdir -p {}/migrations;'.format(constants.ARTIFACT_PATH),
            'export ANSIBLE_HOST_KEY_CHECKING=False;',
            'export ANSIBLE_SSH_ARGS="-o ControlMaster=auto -o ControlPersist=30m";',
            'PRIVATE_KEY=`/bin/pwd`/../{}/key.pem;'.format(constants.ARTIFACT_PATH),
        ],
        inventory='../{}/ansible_inventory '.format(constants.ARTIFACT_PATH),
        extra_options=[
            '--private-key=$PRIVATE_KEY',
            '--user=ubuntu',
            '--module-path=playbooks/library',
        ],
        variables=variables,
        playbook='playbooks/continuous_delivery/run_migrations.yml',
        runif=runif
    ))


def generate_check_migration_duration(job,
                                      input_file,
                                      duration_threshold,
                                      from_address,
                                      to_addresses,
                                      ses_region=None,
                                      runif='passed'):
    """
    Generates a task that checks a migration's duration against a threshold.
    If the threshold is exceeded, alert via email.

    Args:
        job (gomatic.Job): the Job to attach this stage to.
        input_file (str): Name of file containing migration duration.
        duration_threshold (int): Migration threshold in seconds.
        from_address (str): Single "From:" email address for alert email.
        to_addresses (list(str)): List of "To:" email addresses for alert email.
        ses_region (str): AWS region whose SES to use.
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)
    """
    cmd_args = [
        '--migration_file',
        '../{artifact_path}/migrations/{input_file}'.format(
            artifact_path=constants.ARTIFACT_PATH,
            input_file=input_file
        ),
        '--duration_threshold', str(duration_threshold),
        '--instance_data',
        '${GO_SERVER_URL/:8154/}pipelines/${GO_PIPELINE_NAME}/${GO_PIPELINE_COUNTER}'
        '/${GO_STAGE_NAME}/${GO_STAGE_COUNTER}',
        '--from_address', from_address
    ]
    if ses_region:
        cmd_args.extend(('--aws_ses_region', ses_region))
    for email in to_addresses:
        cmd_args.extend(('--alert_email', email))

    return job.add_task(tubular_task(
        'check_migrate_duration.py',
        cmd_args,
        runif=runif,
    ))


def generate_migration_rollback(
        job,
        sub_application_name=None,
        runif="passed"
):
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

    migration_artifact_path = '{}/rollback/migrations'.format(constants.ARTIFACT_PATH)
    generate_target_directory(job, migration_artifact_path)
    job.ensure_artifacts(
        set(
            [BuildArtifact(migration_artifact_path)]
        )
    )

    command = ' '.join(
        [
            'for migration_input_file in ../{migration_artifact_path}/*_migration_plan.yml do',
            'export ANSIBLE_HOST_KEY_CHECKING=False;',
            'export ANSIBLE_SSH_ARGS="-o ControlMaster=auto -o ControlPersist=30m";',
            'PRIVATE_KEY=`/bin/pwd`/../{artifact_path}/key.pem;',
            'ansible-playbook',
            '-vvvv',
            '-i ../{artifact_path}/ansible_inventory',
            '--private-key=$PRIVATE_KEY',
            '--module-path=playbooks/library',
            '--user=ubuntu',
            '-e APPLICATION_PATH=$APPLICATION_PATH',
            '-e APPLICATION_NAME=$APPLICATION_NAME',
            '-e APPLICATION_USER=$APPLICATION_USER',
            '-e ARTIFACT_PATH=`/bin/pwd`/../{artifact_path}/migrations',
            '-e DB_MIGRATION_USER=$DB_MIGRATION_USER',
            '-e DB_MIGRATION_PASS=$DB_MIGRATION_PASS',
            '-e ../{artifact_path}/${{migration_input_file}}'
        ]
    )

    command = command.format(
        artifact_path=constants.ARTIFACT_PATH,
        migration_artifact_path=migration_artifact_path
    )
    if sub_application_name is not None:
        command += ' -e SUB_APPLICATION_NAME={sub_application_name} '.format(sub_application_name=sub_application_name)

    command += ' playbooks/continuous_delivery/rollback_migrations.yml done || exit'

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
    return job.add_task(tubular_task(
        'format_rsa_key.py',
        prefix=[
            'touch {} &&'.format(output_path),
            'chmod 600 {} &&'.format(output_path),
        ],
        arguments=['--key', '"{}"'.format(key), '--output-file', output_path],
    ))


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
    return job.add_task(bash_task(
        """\
            touch github_key.pem &&
            chmod 600 github_key.pem &&
            format_rsa_key.py --key "$PRIVATE_GITHUB_KEY" --output-file github_key.pem &&
            GIT_SSH_COMMAND='/usr/bin/ssh -o StrictHostKeyChecking=no -i github_key.pem'
            /usr/bin/git clone ${secure_repo_envvar} {secure_dir} &&
            cd {secure_dir} &&
            /usr/bin/git checkout ${secure_version_envvar} &&
            [ -d ../{artifact_path}/ ] && echo "Target Directory Exists" || mkdir ../{artifact_path}/ &&
            /usr/bin/git rev-parse HEAD > ../{artifact_path}/{secure_repo_name}_sha
        """,
        secure_dir=secure_dir,
        secure_repo_envvar=secure_repo_envvar,
        secure_version_envvar=secure_version_envvar,
        secure_repo_name=secure_repo_name,
        artifact_path=constants.ARTIFACT_PATH,
        runif=runif,
    ))


def generate_target_directory(job, directory_name=constants.ARTIFACT_PATH, runif="passed"):
    """
    Add a task to ``job`` that creates the specified directory ``directory_name``.

    Arguments:
        job (gomatic.Job): The job to add this task to.
        directory_name (str): The name of the directory to create. (Optional)
        runif (str): What state the job must be in to run this task.
    """
    return job.ensure_task(bash_task(
        'mkdir -p {dir_name}',
        dir_name=directory_name,
        runif=runif,
    ))


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
        "edx-mktg",
        runif=runif,
    )


def generate_run_app_playbook(
        pipeline, job, playbook_with_path, edp, app_repo,
        launch_artifacts_base_path=None,
        private_github_key='', hipchat_token='',
        hipchat_room=constants.HIPCHAT_ROOM,
        configuration_secure_dir=constants.PRIVATE_CONFIGURATION_LOCAL_DIR,
        configuration_internal_dir=constants.INTERNAL_CONFIGURATION_LOCAL_DIR,
        runif="passed",
        **kwargs):
    """
    Generates:
        a GoCD task that runs an Ansible playbook against a server inventory.

    Assumes:
        - The play will be run using the continuous delivery ansible config constants.ANSIBLE_CONTINUOUS_DELIVERY_CONFIG
        - The play will be run from the constants.PUBLIC_CONFIGURATION_DIR directory
        - a key file for this host in "{launch_artifacts_base_path}/key.pem"
        - a ansible inventory file "{launch_artifacts_base_path}/ansible_inventory"
        - a launch info file "{launch_artifacts_base_path}/launch_info.yml"

    The calling pipline for this task must have the following materials:
        - edx-secure
        - configuration

        These are generated by edxpipelines.patterns.stages.generate_launch_instance

    Args:
        pipeline (gomatic.Pipeline): the gomatic pipeline to add environment variables to
        job (gomatic.job.Job): the gomatic job to which the playbook run task will be added
        playbook_with_path (str): path to playbook relative to the top-level 'configuration' directory
        edp (EDP):
        app_repo (str) :
        launch_artifacts_base_path (str): Path containing the launch artifacts. Defaults to constants.ARTIFACT_PATH
        private_github_key (str):
        hipchat_token (str):
        hipchat_room (str):
        manual_approval (bool):
        configuration_internal_dir (str): The internal config directory to use for this play.
        configuration_secure_dir (str): The secure config directory to use for this play.
        runif (str): one of ['passed', 'failed', 'any'] Default: passed
        **kwargs (dict):
            k,v pairs:
                k: the name of the option to pass to ansible
                v: the value to use for this option

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """
    if not launch_artifacts_base_path:
        launch_artifacts_base_path = constants.ARTIFACT_PATH

    # Set up the necessary environment variables.
    pipeline.ensure_encrypted_environment_variables(
        {
            'HIPCHAT_TOKEN': hipchat_token,
            'PRIVATE_GITHUB_KEY': private_github_key
        }
    )
    pipeline.ensure_environment_variables(
        {
            'PLAY': edp.play,
            'DEPLOYMENT': edp.deployment,
            'EDX_ENVIRONMENT': edp.environment,
            'APP_REPO': app_repo,
            'ARTIFACT_PATH': '{}/'.format(constants.ARTIFACT_PATH),
            'HIPCHAT_ROOM': hipchat_room,
            'ANSIBLE_CONFIG': constants.ANSIBLE_CONTINUOUS_DELIVERY_CONFIG,
        }
    )

    return job.add_task(ansible_task(
        prefix=[
            'chmod 600 ../{}/key.pem;'.format(launch_artifacts_base_path),
            'export ANSIBLE_HOST_KEY_CHECKING=False;',
            'export ANSIBLE_SSH_ARGS="-o ControlMaster=auto -o ControlPersist=30m";',
            'PRIVATE_KEY=$(/bin/pwd)/../{}/key.pem;'.format(launch_artifacts_base_path),
        ],
        extra_options=[
            '--private-key=$PRIVATE_KEY',
            '--user=ubuntu',
            '--module-path=playbooks/library',
        ],
        inventory='../{}/ansible_inventory '.format(launch_artifacts_base_path),
        variables=[
            '{}/launch_info.yml'.format(launch_artifacts_base_path),
            '{}/ansible/vars/${{DEPLOYMENT}}.yml'.format(configuration_internal_dir),
            '{}/ansible/vars/${{EDX_ENVIRONMENT}}-${{DEPLOYMENT}}.yml'.format(configuration_internal_dir),
            '{}/ansible/vars/${{DEPLOYMENT}}.yml'.format(configuration_secure_dir),
            '{}/ansible/vars/${{EDX_ENVIRONMENT}}-${{DEPLOYMENT}}.yml'.format(configuration_secure_dir),
        ] + sorted(kwargs.items()),
        playbook=playbook_with_path,
        runif=runif
    ))


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
    return job.add_task(tubular_task(
        'drupal_backup_database.py',
        [
            '--env', site_env,
            '--username $PRIVATE_ACQUIA_USERNAME',
            '--password $PRIVATE_ACQUIA_PASSWORD',
        ]
    ))


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
    return job.add_task(bash_task(
        'drush -y @edx.{site_env} cc all',
        site_env=site_env,
        working_dir='edx-mktg/docroot',
    ))


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
    return job.add_task(tubular_task(
        'drupal_clear_varnish.py',
        [
            '--env', site_env,
            '--username $PRIVATE_ACQUIA_USERNAME',
            '--password $PRIVATE_ACQUIA_PASSWORD',
        ]
    ))


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
    return job.add_task(tubular_task(
        'drupal_deploy.py',
        [
            '--env', site_env,
            '--username $PRIVATE_ACQUIA_USERNAME',
            '--password $PRIVATE_ACQUIA_PASSWORD',
            '--tag $(cat ../{artifact_path}/{tag_file})'.format(
                tag_file=tag_file,
                artifact_path=constants.ARTIFACT_PATH,
            )
        ]
    ))


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
    return job.add_task(tubular_task(
        'drupal_fetch_deployed_tag.py',
        [
            '--env', site_env,
            '--username $PRIVATE_ACQUIA_USERNAME',
            '--password $PRIVATE_ACQUIA_PASSWORD',
            '--path_name', path_name,
        ]
    ))


def generate_refresh_metadata(job, runif='passed'):
    """
    Generates GoCD task that refreshes metadata (for the Catalog Service) via an Ansible script.

    Args:
        job (gomatic.job.Job): the gomatic job to which the run migrations task will be added
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """

    return job.add_task(ansible_task(
        prefix=[
            'export ANSIBLE_HOST_KEY_CHECKING=False;',
            'export ANSIBLE_SSH_ARGS="-o ControlMaster=auto -o ControlPersist=30m";',
            'PRIVATE_KEY=`/bin/pwd`/../../key.pem;',
        ],
        inventory='../../ansible_inventory',
        extra_options=[
            '--private-key=$PRIVATE_KEY',
            '--user=ubuntu',
        ],
        variables=[
            ('APPLICATION_PATH', '$APPLICATION_PATH'),
            ('APPLICATION_NAME', '$APPLICATION_NAME'),
            ('APPLICATION_USER', '$APPLICATION_USER'),
            ('HIPCHAT_TOKEN', '$HIPCHAT_TOKEN'),
            ('HIPCHAT_ROOM', '"$HIPCHAT_ROOM"'),
        ],
        playbook='discovery_refresh_metadata.yml',
        working_dir='configuration/playbooks/continuous_delivery/',
        runif=runif
    ))


def generate_update_index(job, runif='passed'):
    """
    Generates GoCD task that runs the Haystack update_index management command via an Ansible script.

    Args:
        job (gomatic.job.Job): the gomatic job to which the run migrations task will be added
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """
    return job.add_task(ansible_task(
        prefix=[
            'export ANSIBLE_HOST_KEY_CHECKING=False;',
            'export ANSIBLE_SSH_ARGS="-o ControlMaster=auto -o ControlPersist=30m";',
            'PRIVATE_KEY=`/bin/pwd`/../../key.pem;',
        ],
        inventory='../../ansible_inventory',
        extra_options=[
            '--private-key=$PRIVATE_KEY',
            '--user=ubuntu',
        ],
        variables=[
            ('APPLICATION_PATH', '$APPLICATION_PATH'),
            ('APPLICATION_NAME', '$APPLICATION_NAME'),
            ('APPLICATION_USER', '$APPLICATION_USER'),
            ('HIPCHAT_TOKEN', '$HIPCHAT_TOKEN'),
            ('HIPCHAT_ROOM', '"$HIPCHAT_ROOM"'),
        ],
        playbook='haystack_update_index.yml',
        working_dir='configuration/playbooks/continuous_delivery/',
        runif=runif,
    ))


def generate_create_release_candidate_branch_and_pr(job,
                                                    org,
                                                    repo,
                                                    source_branch,
                                                    target_branch,
                                                    pr_target_branch,
                                                    runif='passed'):
    """
    Assumptions:
        Assumes a secure environment variable named "GIT_TOKEN"

    Args:
        job (gomatic.Job): the Job to attach this stage to.
        org (str): Name of the github organization that holds the repository (e.g. edx)
        repo (str): Name of repository (e.g edx-platform)
        source_branch (str): Name of the branch to create the branch/PR from
        target_branch (str): Name of the branch to be created (will be the head of the PR)
        pr_target_branch (str): The base branch of the pull request (merge target_branch in to pr_target_branch)
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """
    return job.add_task(tubular_task(
        'create_release_candidate.py',
        [
            '--org', org,
            '--repo', repo,
            '--source_branch', source_branch,
            '--target_branch', target_branch,
            '--pr_target_branch', pr_target_branch,
            '--token $GIT_TOKEN',
        ],
        runif=runif,
    ))


def generate_create_branch(pipeline,
                           job,
                           token,
                           org,
                           repo,
                           target_branch,
                           runif='passed',
                           source_branch=None,
                           sha=None):
    """
    Assumptions:
        Assumes a secure environment variable named "GIT_TOKEN"

    Args:
        pipeline (gomatic.Pipeline): The Pipeline to insert environment variables into.
        job (gomatic.Job): the Job to attach this stage to.
        token (str): The github token to use with the API.
        org (str): Name of the github organization that holds the repository (e.g. edx)
        repo (str): Name of repository (e.g edx-platform)
        target_branch (str): Name of the branch to be created (will be the head of the PR)
        runif (str): one of ['passed', 'failed', 'any'] Default: passed
        source_branch (str): Name (or environment variable) of the branch to create the branch/PR from
        sha (str): SHA (or environment variable) of the commit to create the branch/PR from

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """
    pipeline.ensure_unencrypted_secure_environment_variables(
        {
            'GIT_TOKEN': token
        }
    )

    generate_target_directory(job)

    args = [
        '--org', org,
        '--repo', repo,
        '--target_branch', target_branch,
        '--token', '$GIT_TOKEN',
        '--output_file', '../{artifact_path}/{output_file}'.format(
            artifact_path=constants.ARTIFACT_PATH,
            output_file=constants.CREATE_BRANCH_FILENAME
        )
    ]

    if source_branch:
        args.extend(['--source_branch', source_branch])

    if sha:
        args.extend(['--sha', sha])

    return job.add_task(tubular_task(
        'cut_branch.py',
        args,
        runif=runif,
    ))


def generate_create_pr(job,
                       org,
                       repo,
                       source_branch,
                       target_branch,
                       title,
                       body,
                       runif='passed'):
    """
    Assumptions:
        Assumes a secure environment variable named "GIT_TOKEN"

    Args:
        job (gomatic.Job): the Job to attach this stage to.
        org (str): Name of the github organization that holds the repository (e.g. edx)
        repo (str): Name of repository (e.g edx-platform)
        source_branch (str): Name of the branch to create the branch/PR from
        target_branch (str): Name of the branch to be created (will be the head of the PR)
        title (str): Title to use for the created PR
        body (str): Body to use for the created PR
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)
    """
    output_file_path = '{}/{}'.format(
        constants.ARTIFACT_PATH,
        constants.CREATE_BRANCH_PR_FILENAME
    )
    job.ensure_artifacts(set([BuildArtifact(output_file_path)]))

    cmd_args = [
        '--org', org,
        '--repo', repo,
        '--source_branch', source_branch,
        '--target_branch', target_branch,
        '--title "{}"'.format(title),
        '--body "{}"'.format(body),
        '--token $GIT_TOKEN',
        '--output_file ../{}'.format(output_file_path),
    ]

    return job.add_task(tubular_task(
        'create_pr.py',
        cmd_args,
        runif=runif
    ))


def generate_merge_branch(
        pipeline, job, token, org, repo, source_branch, target_branch,
        fast_forward_only, runif='passed'
):
    """
    Args:
        pipeline (gomatic.Pipeline): the Pipeline to add environment variables to.
        job (gomatic.Job): the Job to attach this stage to.
        token (str): the github token to use to communicate with github.
        org (str): Name of the github organization that holds the repository (e.g. edx)
        repo (str): Name of repository (e.g edx-platform)
        source_branch (str): Name of the branch to merge into the target branch
        target_branch (str): Name of the branch into which to merge the source branch
        fast_forward_only (bool): If True, force a fast-forward merge or fail.
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """
    pipeline.ensure_unencrypted_secure_environment_variables(
        {
            'GIT_TOKEN': token
        }
    )

    output_file_path = '{}/{}'.format(
        constants.ARTIFACT_PATH,
        constants.MERGE_BRANCH_FILENAME
    )
    job.ensure_artifacts(set([BuildArtifact(output_file_path)]))

    cmd_args = [
        '--org', org,
        '--repo', repo,
        '--source_branch', source_branch,
        '--target_branch', target_branch,
        '--output_file ../{}'.format(output_file_path)
    ]
    if fast_forward_only:
        cmd_args.append('--fast_forward_only')

    return job.add_task(tubular_task(
        'merge_branch.py',
        cmd_args,
        runif=runif,
    ))


def generate_merge_pr(job,
                      org,
                      repo,
                      input_file,
                      runif='passed'):
    """
    Assumptions:
        Assumes a secure environment variable named "GIT_TOKEN"

    Args:
        job (gomatic.Job): the Job to attach this stage to.
        org (str): Name of the github organization that holds the repository (e.g. edx)
        repo (str): Name of repository (e.g edx-platform)
        input_file (str): Path to YAML file containing PR number, using "pr_id" key
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)
    """
    cmd_args = [
        '--org', org,
        '--repo', repo,
        '--input_file ../{}/{}'.format(constants.ARTIFACT_PATH, input_file),
        '--token $GIT_TOKEN',
    ]

    return job.add_task(tubular_task(
        'merge_pr.py',
        cmd_args,
        runif=runif
    ))


def generate_tag_commit(job,
                        org,
                        repo,
                        input_file=None,
                        commit_sha=None,
                        branch_name=None,
                        deploy_artifact_filename=None,
                        tag_name=None,
                        tag_message=None,
                        runif='passed'):
    """
    Generates a task that tags a commit SHA, passed in these ways:
    - input YAML file containing a 'sha' key
    - explicitly passed-in commit SHA
    - HEAD sha obtained from passed-in branch_name

    Assumptions:
        Assumes a secure environment variable named "GIT_TOKEN"

    Args:
        job (gomatic.Job): the Job to attach this stage to.
        org (str): Name of the github organization that holds the repository (e.g. edx)
        repo (str): Name of repository (e.g edx-platform)
        input_file (str): Name of file containing commit SHA.
        commit_sha (str): Commit SHA to tag.
        branch_name (str): Branch name whose HEAD will be tagged.
        deploy_artifact_filename (str): Filename of the deploy artifact.
        tag_name (str): Name to use for the commit tag.
        tag_message (str): Message to use for the commit tag.
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """
    cmd_args = [
        '--org', org,
        '--repo', repo,
        '--token $GIT_TOKEN',
    ]
    if input_file:
        cmd_args.append('--input_file ../{artifact_path}/{input_file}'.format(
            artifact_path=constants.ARTIFACT_PATH,
            input_file=input_file
        ))
    if commit_sha:
        cmd_args.extend(('--commit_sha', commit_sha))
    if branch_name:
        cmd_args.extend(('--branch_name', branch_name))
    if tag_name:
        cmd_args.extend(('--tag_name', tag_name))
    if tag_message:
        cmd_args.extend(('--tag_message', tag_message))
    if deploy_artifact_filename:
        cmd_args.append('--deploy_artifact ../{artifact_path}/{deploy_artifact_filename}'.format(
            artifact_path=constants.ARTIFACT_PATH,
            deploy_artifact_filename=deploy_artifact_filename
        ))

    return job.add_task(tubular_task(
        'create_tag.py',
        cmd_args,
        runif=runif
    ))


def generate_check_pr_tests(job,
                            org,
                            repo,
                            input_file,
                            runif='passed'):
    """
    Assumptions:
        Assumes a secure environment variable named "GIT_TOKEN"

    Args:
        job (gomatic.Job): the Job to attach this stage to.
        org (str): Name of the github organization that holds the repository (e.g. edx)
        repo (str): Name of repository (e.g edx-platform)
        input_file (str): Name of YAML file containing PR id.
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """
    cmd_args = [
        '--org', org,
        '--repo', repo,
        '--input_file ../{}/{}'.format(constants.ARTIFACT_PATH, input_file),
        '--token $GIT_TOKEN',
    ]
    return job.add_task(tubular_task(
        'check_pr_tests_status.py',
        cmd_args,
        runif=runif
    ))


def generate_poll_pr_tests(job,
                           org,
                           repo,
                           input_file,
                           runif='passed'):
    """
    Assumptions:
        Assumes a secure environment variable named "GIT_TOKEN"

    Args:
        job (gomatic.Job): the Job to attach this stage to.
        org (str): Name of the github organization that holds the repository (e.g. edx)
        repo (str): Name of repository (e.g edx-platform)
        input_file (str): Name of YAML file containing PR id.
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        The newly created task (gomatic.gocd.tasks.ExecTask)

    """
    cmd_args = [
        '--org', org,
        '--repo', repo,
        '--input_file ../{}/{}'.format(constants.ARTIFACT_PATH, input_file),
        '--token $GIT_TOKEN',
    ]

    return job.add_task(tubular_task(
        'poll_pr_tests_status.py',
        cmd_args,
        runif=runif
    ))


def trigger_jenkins_build(
        job, jenkins_url, jenkins_user_name, jenkins_job_name,
        jenkins_params, timeout=30 * 60
):
    """
    Generate a GoCD task that triggers a jenkins build and polls for its results.

    Assumes:
        secure environment variables:
            - JENKINS_USER_TOKEN: API token for the user. Available at {url}/user/{user_name)/configure
            - JENKINS_JOB_TOKEN: Authorization token for the job. Must match that configured in the job definition.

    Args:
        job (gomatic.job.Job): the gomatic job to which this task will be added
        jenkins_url (str): base URL for the jenkins server
        jenkins_user_name (str): username on the jenkins system
        jenkins_job_name (str): name of the jenkins job to trigger
        jenkins_param (dict): parameter names and values to pass to the job
    """
    command = [
        '--url', jenkins_url,
        '--user_name', jenkins_user_name,
        '--job', jenkins_job_name,
        '--cause "Triggered by GoCD Pipeline ${GO_PIPELINE_NAME} build ${GO_PIPELINE_LABEL}"',
        '--timeout', str(timeout)
    ]
    command.extend(
        '--param {} {}'.format(name, value)
        for name, value in jenkins_params.items()
    )

    return job.add_task(tubular_task(
        'jenkins_trigger_build.py',
        command,
    ))


def generate_message_pull_requests_in_commit_range(
        job, org, repo, token, head_sha, release_status,
        runif='passed', base_sha=None, base_ami_artifact=None, ami_tag_app=None
):
    """
    Generate a GoCD task that will message a set of pull requests within a range of commits.

    If base_sha is not supplied, then base_ami_artifact and ami_tag_app must both be supplied.

    Args:
        job (gomatic.job.Job): the gomatic job to which this task will be added
        org (str): The github organization
        repo (str): The github repository
        token (str): The authentication token
        head_sha (str): The ending SHA
        release_status (ReleaseStatus): type of message to send one of
            ['release_stage', 'release_prod', 'release_rollback']
        runif (str): one of ['passed', 'failed', 'any'] Default: passed
        base_sha (str): The sha to use as the base point for sending messages
            (any commits prior to this sha won't be messaged). (Optional)
        base_ami_artifact (ArtifactLocation): The location of the artifact that specifies
            the base_ami and tags (Optional)
        ami_tag_app (str): The name of the version tag on the AMI to extract the version from (Optional)


    Returns:
        gomatic.task.Task
    """
    flag_for_release_status = {
        constants.ReleaseStatus.STAGED: 'release_stage',
        constants.ReleaseStatus.DEPLOYED: 'release_prod',
        constants.ReleaseStatus.ROLLED_BACK: 'release_rollback',
    }

    arguments = [
        '--org', org,
        '--token', token,
        '--repo', repo,
        '--head_sha', head_sha,
        '--{}'.format(flag_for_release_status[release_status])
    ]
    if base_sha:
        arguments.extend(['--base_sha', base_sha])

    if base_ami_artifact and ami_tag_app:
        retrieve_artifact(base_ami_artifact, job, constants.ARTIFACT_PATH)

        arguments.extend([
            '--base_ami_tags', "../{}/{}".format(constants.ARTIFACT_PATH, base_ami_artifact.file_name),
            '--ami_tag_app', ami_tag_app,
        ])
    elif base_ami_artifact or ami_tag_app:
        raise ValueError(
            "Both base_ami_artifact ({!r}) and ami_tag_app"
            "({!r}) must be specified together".format(
                base_ami_artifact, ami_tag_app
            )
        )

    return job.add_task(tubular_task(
        'message_prs_in_range.py',
        arguments,
        runif=runif,
    ))


def generate_release_wiki_page(
        pipeline, job, confluence_user, confluence_password, github_token,
        release_status, ami_pairs, parent_title=None,
        space=None, title=None, input_artifact=None,
):
    """
    Generate a release page on the wiki for all of the amis specified in ``ami_pairs``.

    Arguments:
        pipeline (gomatic.Pipeline): The pipeline to add this task to.
        job (gomatic.Job): The job to add this task to.
        confluence_user (str): The username of the confluence user to post as.
        confluence_password (str): The password of the confluence user to post as.
        github_token (str): The github token to use when reading PR data from github.
        release_status (ReleaseStatus): The current status of the release.
        ami_pairs (list): A list of pairs of ArtifactLocations ``(base, new)``.
            ``base`` specifies the location of the AMI description yml file of the
            base AMI used to build ``new``. ``new`` specifies the location of the
            AMI description yml file for the AMI being deployed.
        parent_title (str): The title of the wiki page to post the new wiki page under.
        space (str): The space to post the new wiki page to.
        title (str): The title to post the wiki page with.
        input_artifact (ArtifactLocation): The location of the RELEASE_WIKI_PAGE_ID_FILENAME
            generated by a previous publication of a wiki page. Identifies which wiki
            page to update. Mutually exclusive with parent_title/space/title.
    """
    if input_artifact and any([parent_title, space, title]):
        raise ValueError("input_artifact and parent_title/space/title are mutually exclusive.")

    pipeline.ensure_unencrypted_secure_environment_variables(
        {
            'CONFLUENCE_PASSWORD': confluence_password,
            'GITHUB_TOKEN': github_token,
        }
    )

    wiki_id = '{}/{}'.format(
        constants.ARTIFACT_PATH,
        constants.RELEASE_WIKI_PAGE_ID_FILENAME,
    )

    job.ensure_artifacts(set([BuildArtifact(wiki_id)]))

    arguments = [
        '--user', confluence_user,
        '--password', '$CONFLUENCE_PASSWORD',
        '--github-token', '$GITHUB_TOKEN',
        '--status', release_status.value,
        '--out-file', wiki_id,
    ]

    if input_artifact:
        input_wiki_id_folder = '{}/{}'.format(constants.ARTIFACT_PATH, input_artifact.pipeline)
        arguments.extend([
            '--in-file',
            '{}/{}'.format(input_wiki_id_folder, input_artifact.file_name),
        ])
        retrieve_artifact(input_artifact, job, input_wiki_id_folder)
    else:
        if parent_title:
            arguments.extend(['--parent-title', parent_title])
        if space:
            arguments.extend(['--space', space])
        if title:
            arguments.extend(['--title', title])

    for base, new in ami_pairs:
        compare_option = ['--compare']
        for artifact in (base, new):
            output_dir = '{}/{}'.format(constants.ARTIFACT_PATH, artifact.pipeline)
            compare_option.append("{}/{}".format(output_dir, artifact.file_name))
            retrieve_artifact(artifact, job, output_dir)
        arguments.extend(compare_option)

    return job.add_task(tubular_task(
        'update_release_page.py',
        arguments,
        working_dir=None,
    ))


def generate_base_ami_selection(
        pipeline, job, aws_access_key_id, aws_secret_access_key,
        play=None, deployment=None, edx_environment=None,
        base_ami_id=None
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

    # Generate an base-AMI-ID-overriding artifact.
    base_ami_override_artifact = '{artifact_path}/{file_name}'.format(
        artifact_path=constants.ARTIFACT_PATH,
        file_name=constants.BASE_AMI_OVERRIDE_FILENAME
    )
    job.ensure_artifacts(set([BuildArtifact(base_ami_override_artifact)]))
    job.add_task(bash_task(
        """\
            mkdir -p {artifact_path};
            if [[ $BASE_AMI_ID_OVERRIDE != 'yes' ]];
                then echo "Finding base AMI ID from active ELB/ASG in EDP.";
                {ami_script}
                    --environment $EDX_ENVIRONMENT
                    --deployment $DEPLOYMENT
                    --play $PLAY
                    --out_file {override_artifact};
            elif [[ -n $BASE_AMI_ID ]];
                then echo "Using specified base AMI ID of '$BASE_AMI_ID'";
                {ami_script} --override $BASE_AMI_ID --out_file {override_artifact};
            else echo "Using environment base AMI ID";
                echo "{empty_dict}" > {override_artifact}; fi;
        """,
        artifact_path='../' + constants.ARTIFACT_PATH,
        ami_script='retrieve_base_ami.py',
        empty_dict='{}',
        override_artifact='../' + base_ami_override_artifact,
        working_dir="tubular",
        runif="passed"
    ))
