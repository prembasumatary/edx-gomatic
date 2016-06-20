from gomatic import *


def generate_install_requirements(job, working_dir):
    """
    Generates a command that runs:
    'sudo pip install -r requirements.txt'

    Args:
        job (gomatic.job.Job): the gomatic job which to add install requirements
        working_dir (str): the directory gocd should run the install command from

    Returns:
        gomatic.task.Task

    """
    return job.add_task(ExecTask(['/bin/bash', '-c', 'sudo pip install -r requirements.txt'], working_dir=working_dir))
