# Names for the standard stages/jobs
DEPLOY_AMI_STAGE_NAME = 'deploy_ami'
DEPLOY_AMI_JOB_NAME = 'deploy_ami_job'
RUN_MIGRATIONS_STAGE_NAME = 'apply_migrations'
RUN_MIGRATIONS_JOB_NAME = 'apply_migrations_job'
BUILD_AMI_STAGE_NAME = 'build_ami'
BUILD_AMI_JOB_NAME = 'build_ami_job'
TERMINATE_INSTANCE_STAGE_NAME = 'cleanup_ami_Instance'
TERMINATE_INSTANCE_JOB_NAME = 'cleanup_ami_instance_job'
LAUNCH_INSTANCE_STAGE_NAME = 'launch_instance'
LAUNCH_INSTANCE_JOB_NAME = 'launch_instance_job'
RUN_PLAY_STAGE_NAME = "run_play"
RUN_PLAY_JOB_NAME = "run_play_job"

# Defaults
ARTIFACT_PATH = 'target'
PUBLIC_CONFIGURATION_REPO_URL='https://github.com/edx/configuration.git'
PUBLIC_CONFIGURATION_REPO_BRANCH='master'
PRIVATE_CONFIGURATION_REPO_BRANCH='master'
PRIVATE_CONFIGURATION_LOCAL_DIR='secure_repo'
APP_REPO_BRANCH='master'
HIPCHAT_ROOM='release'

## AWS Defaults
EC2_REGION='us-east-1'
EC2_INSTANCE_TYPE='t2.large'
EC2_LAUNCH_INSTANCE_TIMEOUT='300'
EC2_EBS_VOLUME_SIZE='50'


