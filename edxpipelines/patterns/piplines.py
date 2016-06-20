from gomatic import *
from edxpipelines.patterns import stages, jobs


def generate_deploy_pipeline(configurator,
                             pipeline_name,
                             pipeline_group,
                             asgard_api_endpoints,
                             asgard_token,
                             aws_access_key_id,
                             aws_secret_access_key):
    """

    Args:
        configurator (GoCdConfigurator)
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
        .ensure_pipeline_group(pipeline_group) \
        .ensure_replacement_of_pipeline(pipeline_name) \
        .set_git_material(
            GitMaterial("https://github.com/edx/tubular.git", polling=False, destination_directory="tubular"))
    stages.generate_basic_deploy_ami(pipeline, asgard_api_endpoints, asgard_token, aws_access_key_id, aws_secret_access_key)
    return configurator
