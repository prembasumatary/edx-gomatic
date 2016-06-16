from gomatic import *


def generate_deploy_pipeline(configurator, **kwargs):
    """

    Args:
        configurator (GoCdConfigurator)

        **kwargs:
            pipeline_name (str):
            pipeline_group (str):
            asgard_api_endpoints (str): url of the asgard API
            asgard_token (str):
            aws_access_key_id (str):
            aws_secret_access_key (str):

    Returns:
        GoCdConfigurator
    """

    pipeline = configurator \
        .ensure_pipeline_group(kwargs['pipeline_group']) \
        .ensure_replacement_of_pipeline(kwargs['pipeline_name']) \
        .set_git_material(
            GitMaterial("https://github.com/edx/tubular.git", polling=False, destination_directory="tubular")) \
                .ensure_environment_variables({'AMI_ID': None,
                                               'ASGARD_API_ENDPOINTS': kwargs['asgard_api_endpoints']}) \
                .ensure_encrypted_environment_variables(
                    {'ASGARD_API_TOKEN': kwargs['asgard_token'],
                     'AWS_ACCESS_KEY_ID': kwargs['aws_access_key_id'],
                     'AWS_SECRET_ACCESS_KEY': kwargs['aws_secret_access_key']
                })

    stage = pipeline.ensure_stage("Deploy_AMI").set_has_manual_approval()
    job = stage.ensure_job("Deploy_AMI")
    job.add_task(ExecTask(['/bin/bash', '-c', 'sudo pip install -r requirements.txt'], working_dir="tubular"))
    job.add_task(ExecTask(['/usr/bin/python', 'scripts/asgard-deploy.py'], working_dir="tubular"))

    return configurator

