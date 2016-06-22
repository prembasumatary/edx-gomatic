from gomatic import *


def generate_install_requirements(job, working_dir, runif="passed"):
    """
    Generates a command that runs:
    'sudo pip install -r requirements.txt'

    Args:
        job (gomatic.job.Job): the gomatic job which to add install requirements
        working_dir (str): the directory gocd should run the install command from
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        gomatic.task.Task

    """
    return job.add_task(ExecTask(['/bin/bash', '-c', 'sudo pip install -r requirements.txt'], working_dir=working_dir, runif=runif))


def generate_launch_instance(job, runif="passed"):
    """
    Generate the launch AMI job. This ansible script generates 2 artifacts:
        key.pem         - Key material generated for this instance launch
        launch_info.yml -

    Args:
        job (gomatic.job.Job): the gomatic job which to add the launch instance task
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        gomatic.task.Task

    """
    job.ensure_artifacts(set([BuildArtifact("target/key.pem", "key.pem"),
                             BuildArtifact("target/launch_info.yml", "launch_info.yml")]))
    return job.add_task(ExecTask(['/bin/bash', '-c', 'ansible-playbook '
                                                     '-vvvv '
                                                     '--module-path=../../configuration/playbooks/library '
                                                     '-i "localhost," '
                                                     '-c local '
                                                     '-e artifact_path=`/bin/pwd`/../../../$ARTIFACT_PATH '
                                                     '-e ec2_subnet_id=$EC2_SUBNET_ID '
                                                     '-e base_ami_id=$BASE_AMI_ID '
                                                     '-e ec2_vpc_subnet_id=$EC2_VPC_SUBNET_ID '
                                                     '-e ec2_security_group_id=$EC2_SECURITY_GROUP_ID '
                                                     '-e ec2_instance_type=$EC2_INSTANCE_TYPE '
                                                     'launch_instance.yml'],
                                    working_dir="configuration/playbooks/continuous_delivery/",
                                    runif=runif
                                 )
                         )


def generate_create_edxapp_ami(job, runif="passed"):
    """
    TODO: Decouple AMI building and AMI tagging in to 2 different jobs/anislbe scripts

    Args:
        job (gomatic.job.Job): the gomatic job which to add the launch instance task
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        gomatic.task.Task

    """
    job.ensure_artifacts(set([BuildArtifact("target/ami.yml", "ami.yml")]))
    job.add_task(ExecTask(['/bin/bash', '-c', 'ansible-playbook '
                                              '-vvvv '
                                              '--module-path=../../playbooks/library '
                                              '-i "localhost," '
                                              '-c local '
                                              '-e @../../../target/launch_info.yml '
                                              '-e play=$PLAY '
                                              '-e deployment=$DEPLOYMENT '
                                              '-e edx_environment=$EDX_ENVIRONMENT '
                                              '-e cluster_repo=$CLUSTER_REPO '
                                              '-e cluster_version=$CLUSTER_VERSION '
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
                                              'create_ami.yml'],
                          working_dir="configuration/playbooks/continuous_delivery/",
                          runif=runif
                          )
                 )


def generate_create_ami(job, runif="passed"):
    """
    TODO: Decouple AMI building and AMI tagging in to 2 different jobs/anislbe scripts

    Args:
        job (gomatic.job.Job): the gomatic job which to add the launch instance task
        runif (str): one of ['passed', 'failed', 'any'] Default: passed

    Returns:
        gomatic.task.Task

    """
    job.ensure_artifacts(set([BuildArtifact("target/ami.yml", "ami.yml")]))
    job.add_task(ExecTask(['/bin/bash', '-c', 'ansible-playbook '
                                              '-vvvv '
                                              '--module-path=../../playbooks/library '
                                              '-i "localhost," '
                                              '-c local '
                                              '-e @../../../target/launch_info.yml '
                                              '-e play=$PLAY '
                                              '-e deployment=$DEPLOYMENT '
                                              '-e edx_environment=$EDX_ENVIRONMENT '
                                              '-e cluster_repo=$CLUSTER_REPO '
                                              '-e cluster_version=$CLUSTER_VERSION '
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
                                              'create_ami.yml'],
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

    """
    return job.add_task(ExecTask(['/bin/bash', '-c', 'ansible-playbook '
                                               '-vvvv '
                                               '--module-path=../../configuration/playbooks/library '
                                               '-i "localhost," '
                                               '-c local '
                                               '-e @../../../target/launch_info.yml '
                                               '-e ec2_region=$EC2_REGION '
                                               '-e hipchat_token=$HIPCHAT_TOKEN '
                                               '-e hipchat_room="$HIPCHAT_ROOM" '
                                              'cleanup.yml'],
                                 working_dir="configuration/playbooks/continuous_delivery/",
                                 runif=runif
                                )
                        )
