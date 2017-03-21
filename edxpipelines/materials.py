"""
A set of standard overridable material definitions.
"""
from functools import partial

from gomatic import GitMaterial


def deployment_secure(deployment, branch='master', polling=True, destination_directory=None, ignore_patterns=None):
    """
    Initialize a GitMaterial representing a deployment's secure configuration repo.

    Args:
        deployment (str): Deployment for which to create the material (e.g., 'edx', 'edge')

    Returns:
        gomatic.gomatic.gocd.materials.GitMaterial
    """
    return GitMaterial(
        url='git@github.com:edx-ops/{}-secure.git'.format(deployment),
        branch=branch,
        polling=polling,
        destination_directory=destination_directory or '{}-secure'.format(deployment),
        ignore_patterns=ignore_patterns or ['**/*']
    )


def deployment_internal(deployment, branch='master', polling=True, destination_directory=None, ignore_patterns=None):
    """
    Initialize a GitMaterial representing a deployment's internal configuration repo.

    Args:
        deployment (str): Deployment for which to create the material (e.g., 'edx', 'edge')

    Returns:
        gomatic.gomatic.gocd.materials.GitMaterial
    """
    return GitMaterial(
        url='git@github.com:edx/{}-internal.git'.format(deployment),
        branch=branch,
        polling=polling,
        destination_directory=destination_directory or '{}-internal'.format(deployment),
        ignore_patterns=ignore_patterns or ['**/*']
    )


TUBULAR = partial(
    GitMaterial,
    url="https://github.com/edx/tubular",
    branch="master",
    polling=True,
    destination_directory="tubular",
    ignore_patterns=['**/*'],
)

CONFIGURATION = partial(
    GitMaterial,
    url="https://github.com/edx/configuration",
    branch="master",
    polling=True,
    destination_directory="configuration",
    ignore_patterns=['**/*'],
)

EDX_PLATFORM = partial(
    GitMaterial,
    url="https://github.com/edx/edx-platform",
    branch="release-candidate",
    polling=True,
    destination_directory="edx-platform",
    ignore_patterns=['**/*'],
)

EDX_SECURE = partial(deployment_secure, 'edx')

EDGE_SECURE = partial(deployment_secure, 'edge')

EDX_MICROSITE = partial(
    GitMaterial,
    url="git@github.com:edx/edx-microsite.git",
    branch="release",
    polling=True,
    destination_directory="edx-microsite",
    ignore_patterns=['**/*'],
)

EDX_INTERNAL = partial(deployment_internal, 'edx')

EDGE_INTERNAL = partial(deployment_internal, 'edge')

EDX_MKTG = partial(
    GitMaterial,
    url="git@github.com:edx/edx-mktg.git",
    branch="master",
    polling=True,
    destination_directory="edx-mktg",
    ignore_patterns=['**/*'],
)

ECOM_SECURE = partial(
    GitMaterial,
    url="git@github.com:edx-ops/ecom-secure",
    branch="master",
    polling=True,
    destination_directory="ecom-secure",
    ignore_patterns=['**/*'],
)
