from gomatic import *
import edxpipelines.patterns.tasks as tasks


def generate_asg_cleanup(pipeline, asgard_api_endpoints, asgard_token, aws_access_key_id, aws_secret_access_key):
    """

    Args:
        pipeline:
        asgard_api_endpoints:
        asgard_token:
        aws_access_key_id:
        aws_secret_access_key:

    Returns:

    """
    pipeline.ensure_environment_variables({'ASGARD_API_ENDPOINTS': asgard_api_endpoints}) \
            .ensure_encrypted_environment_variables({'ASGARD_API_TOKEN': asgard_token,
                                                     'AWS_ACCESS_KEY_ID': aws_access_key_id,
                                                     'AWS_SECRET_ACCESS_KEY': aws_secret_access_key})

    stage = pipeline.ensure_stage("ASG-Cleanup-Stage")
    job = stage.ensure_job("Cleanup-ASGS")
    tasks.generate_install_requirements(job, 'tubular')
    job.add_task(ExecTask(['/usr/bin/python', 'scripts/cleanup-asgs.py'], working_dir="tubular"))

    return pipeline


def generate_basic_deploy_ami(pipeline, asgard_api_endpoints, asgard_token, aws_access_key_id, aws_secret_access_key):
    """

    Args:
        pipeline (gomatic.Pipeline):
        asgard_api_endpoints (str): canonical URL for asgard.
        asgard_token (str):
        aws_access_key_id (str):
        aws_secret_access_key (str):

    Returns:
        gomatic.Pipeline

    """
    pipeline.ensure_environment_variables({'AMI_ID': None,
                                           'ASGARD_API_ENDPOINTS': asgard_api_endpoints}) \
            .ensure_encrypted_environment_variables({'ASGARD_API_TOKEN': asgard_token,
                                                     'AWS_ACCESS_KEY_ID': aws_access_key_id,
                                                     'AWS_SECRET_ACCESS_KEY': aws_secret_access_key})
    stage = pipeline.ensure_stage("Deploy_AMI").set_has_manual_approval()
    job = stage.ensure_job("Deploy_AMI")
    tasks.generate_install_requirements(job, 'tubular')
    job.add_task(ExecTask(['/usr/bin/python', 'scripts/asgard-deploy.py'], working_dir="tubular"))

    return pipeline


def generate_edp_validation(pipeline,
                            hipchat_auth_token,
                            hipchat_channels,
                            asgard_api_endpoints,
                            ami_deployment,
                            ami_environment,
                            ami_play):
    """

    Args:
        pipeline (gomatic.Pipeline):
        hipchat_auth_token (str):
        hipchat_channels (str): The channels/users to notify
        asgard_api_endpoints (str): canonical URL for asgard.
        ami_deployment (str): typically one of: [edx, edge, etc...]
        ami_environment (str): typically one of: [stage, prod, loadtest, etc...]
        ami_play (str):

    Returns:
        gomatic.Pipeline

    """
    pipeline.ensure_environment_variables({'AMI_ID': None,
                                           'AMI_DEPLOYMENT': ami_deployment,
                                           'HIPCHAT_CHANNELS': hipchat_channels,
                                           'ASGARD_API_ENDPOINTS': asgard_api_endpoints,
                                           'AMI_ENVIRONMENT': ami_environment,
                                           'AMI_PLAY': ami_play})\
            .ensure_encrypted_environment_variables({'HIPCHAT_AUTH_TOKEN': hipchat_auth_token})

    stage = pipeline.ensure_stage("Validation")
    job = stage.ensure_job("EDPValidation")
    tasks.generate_install_requirements(job, 'tubular')
    job.add_task(ExecTask(['/usr/bin/python', 'scripts/validate_edp.py'], working_dir="tubular"))
    job.add_task(ExecTask(['/bin/bash', '-c',
                           '/usr/bin/python scripts/submit_hipchat_msg.py -m "${AMI_ID} is not tagged for ${AMI_ENVIRONMENT}-${AMI_DEPLOYMENT}-${AMI_PLAY}. Are you sure you\'re deploying the right AMI to the right app?" --color "red"'],
                          working_dir="tubular", runif="failed"))

    return pipeline
