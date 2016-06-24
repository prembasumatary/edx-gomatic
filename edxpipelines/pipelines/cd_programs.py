#!/usr/bin/env python
import sys
from os import path
sys.path.append( path.dirname( path.dirname( path.dirname( path.abspath(__file__) ) ) ) )

import click
import edxpipelines.utils as utils
import edxpipelines.patterns.tasks as tasks
import edxpipelines.patterns.stages as stages
from gomatic import *


@click.command()
@click.option('--save-config', 'save_config_locally', envvar='SAVE_CONFIG', help='Save the pipeline configuration xml locally', required=False, default=False)
@click.option('--dry-run', envvar='DRY_RUN', help='do a dry run of  the pipeline installation, and save the pre/post xml configurations locally', required=False, default=False)
@click.option('--variable_file', 'variable_files', multiple=True, help='path to yaml variable file with a dictionary of key/value pairs to be used as variables in the script', required=False, default=[])
@click.option('-e', '--variable', 'cmd_line_vars', multiple=True, help='key/value of a variable used as a replacement in this script', required=False, type=(str, str), nargs=2, default={})
def install_pipeline(save_config_locally, dry_run, variable_files, cmd_line_vars):
    """
    Variables needed for this pipeline:
    - gocd_username
    - gocd_password
    - gocd_url
    - configuration_secure_repo
    - hipchat_token
    - github_private_key
    - aws_access_key_id
    - aws_secret_access_key
    - ec2_vpc_subnet_id
    - ec2_security_group_id
    - ec2_instance_profile_name
    - base_ami_id
    """
    config = utils.merge_files_and_dicts(variable_files, list(cmd_line_vars,))

    configurator = GoCdConfigurator(HostRestClient(config['gocd_url'], config["gocd_username"], config["gocd_password"], ssl=True))
    pipeline = configurator.ensure_pipeline_group("DeployTesting")\
                           .ensure_replacement_of_pipeline("loadtest-edx-programs-cd")\
                           .ensure_material(GitMaterial("https://github.com/edx/tubular",
                                                        material_name="tubular",
                                                        polling=False,
                                                        destination_directory="tubular"))\
                           .ensure_material(GitMaterial("https://github.com/edx/configuration",
                                                        branch="master",
                                                        material_name="configuration",
                                                        polling=False,
                                                        # NOTE if you want to change this, you should set the
                                                        # CONFIGURATION_VERSION environment variable instead
                                                        destination_directory="configuration"))\
                           .ensure_environment_variables({'PLAY': 'programs',
                                                          'DEPLOYMENT': 'edx',
                                                          'EDX_ENVIRONMENT': 'loadtest',
                                                          'APP_REPO': 'https://github.com/edx/programs.git',
                                                          'APP_VERSION': 'pipeline/build_migrate_deploy',
                                                          'CONFIGURATION_REPO': 'https://github.com/edx/configuration.git',
                                                          'CONFIGURATION_VERSION': 'master',
                                                          'CONFIGURATION_SECURE_REPO': config['configuration_secure_repo'],
                                                          'CONFIGURATION_SECURE_VERSION': 'master',
                                                          'EC2_VPC_SUBNET_ID': config['ec2_vpc_subnet_id'],
                                                          'EC2_SECURITY_GROUP_ID': config['ec2_security_group_id'],
                                                          'EC2_ASSIGN_PUBLIC_IP': 'no',
                                                          'EC2_TIMEOUT': '300',
                                                          'EC2_REGION': 'us-east-1',
                                                          'EBS_VOLUME_SIZE': '50',
                                                          'EC2_INSTANCE_TYPE': 't2.large',
                                                          'EC2_INSTANCE_PROFILE_NAME': config['ec2_instance_profile_name'],
                                                          'NO_REBOOT': 'no',
                                                          'BASE_AMI_ID': config['base_ami_id'], # get the last built AMI or rebuild new
                                                          'AMI_CREATION_TIMEOUT': '3600',
                                                          'AMI_WAIT': 'yes',
                                                          'CACHE_ID': '1234', #gocd build number
                                                          'ARTIFACT_PATH': 'target/',
                                                          'HIPCHAT_ROOM': 'release pipeline'})\
                           .ensure_encrypted_environment_variables({'HIPCHAT_TOKEN': config['hipchat_token'],
                                                                    'PRIVATE_GITHUB_KEY': config['github_private_key'],
                                                                    'AWS_ACCESS_KEY_ID': config['aws_access_key_id'],
                                                                    'AWS_SECRET_ACCESS_KEY': config['aws_secret_access_key']})

    stage = pipeline.ensure_stage("Build-AMI")
    job = stage.ensure_job("Build-ami-job").ensure_artifacts(set([BuildArtifact("configuration"),
                                                                  BuildArtifact("target/config_secure_sha"),
                                                                  BuildArtifact("tubular")]))

    # install the requirements
    tasks.generate_install_requirements(job, 'tubular')
    tasks.generate_install_requirements(job, 'configuration')

    # Setup configuration secure
    job.add_task(ExecTask(['/bin/bash',
                           '-c',
                           "touch github_key.pem && "
                           "chmod 600 github_key.pem && "
                           'python tubular/scripts/format_rsa_key.py --key "$PRIVATE_GITHUB_KEY" --output-file github_key.pem && '
                           "GIT_SSH_COMMAND='/usr/bin/ssh -o StrictHostKeyChecking=no -i github_key.pem' /usr/bin/git clone $CONFIGURATION_SECURE_REPO secure_repo && "
                           "cd secure_repo && "
                           "/usr/bin/git checkout $CONFIGURATION_SECURE_VERSION && "
                           "mkdir ../target/ && "
                           "/usr/bin/git rev-parse HEAD > ../target/config_secure_sha"]))

    # Check out the requested version of configuration
    # This is a work around to add the ability to checkout a specific git sha, an option that gocd does not allow.
    job.add_task(ExecTask(['/bin/bash',
                           '-c', "/usr/bin/git fetch && "
                           "/usr/bin/git pull && "
                           "/usr/bin/git checkout $CONFIGURATION_VERSION"],
                          working_dir="configuration/"))

    # Launch instance
    tasks.generate_launch_instance(job)

    # Cleanup EC2
    tasks.generate_ami_cleanup(job, runif='failed')

    # run the edxapp play
    job.add_task(ExecTask(['/bin/bash',
                           '-c',
                           'export ANSIBLE_HOST_KEY_CHECKING=False;'
                           'export ANSIBLE_SSH_ARGS="-o ControlMaster=auto -o ControlPersist=30m";'
                           'PRIVATE_KEY=`/bin/pwd`/../../../${ARTIFACT_PATH}key.pem;'
                           'ansible-playbook '
                           '-vvvv '
                           '--private-key=$PRIVATE_KEY '
                           '--user=ubuntu '
                           '--module-path=configuration/playbooks/library '
                           '-i ../../../target/ansible_inventory '
                           '-e @../../../target/launch_info.yml '
                           '-e @../../../secure_repo/ansible/vars/${EDX_ENVIRONMENT}-${DEPLOYMENT}.yml '
                           '-e @../../../secure_repo/ansible/vars/${DEPLOYMENT}.yml '
                           '-e cache_id=$GO_PIPELINE_COUNTER'
                           '-e PROGRAMS_VERSION=$APP_VERSION '
                           '-e programs_repo=$APP_REPO '
                           '../edx-east/programs.yml'],
                          working_dir="configuration/playbooks/continuous_delivery/"))

    # Create an AMI from the instance
    tasks.generate_create_ami(job)

    # Cleanup EC2
    tasks.generate_ami_cleanup(job, runif='any')

    # Setup the migrations Stage
    # stage = pipeline.ensure_stage("Run-Migrations")
    # job = stage.ensure_job("Start-AMI").ensure_artifacts(set([BuildArtifact("configuration", "configuration"),
    #                                                               BuildArtifact("tubular", "tubular")]))
    #
    # # install the requirements
    # tasks.generate_install_requirements(job, 'tubular')
    # tasks.generate_install_requirements(job, 'configuration')


    # Stage to deploy the programs AMI Goes here
    ami_file_location = utils.ArtifactLocation(pipeline.name, stage.name, job.name, "ami.yml")
    stages.generate_basic_deploy_ami(pipeline,
                                     config['asgard_api_endpoints'],
                                     config['asgard_token'],
                                     config['aws_access_key_id'], config['aws_secret_access_key'], ami_file_location)


    # Stage to terminate the migrations Instance goes here


    configurator.save_updated_config(save_config_locally=save_config_locally, dry_run=dry_run)

if __name__ == "__main__":
    install_pipeline()
