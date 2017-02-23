"""
A set of standard overridable material definitions.
"""
from functools import partial

from gomatic import GitMaterial


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

EDX_SECURE = partial(
    GitMaterial,
    url="git@github.com:edx-ops/edx-secure.git",
    branch="master",
    polling=True,
    destination_directory="edx-secure",
    ignore_patterns=['**/*'],
)

EDGE_SECURE = partial(
    GitMaterial,
    url="git@github.com:edx-ops/edge-secure.git",
    branch="master",
    polling=True,
    destination_directory="edge-secure",
    ignore_patterns=['**/*'],
)

EDX_MICROSITE = partial(
    GitMaterial,
    url="git@github.com:edx/edx-microsite.git",
    branch="release",
    polling=True,
    destination_directory="edx-microsite",
    ignore_patterns=['**/*'],
)

EDX_INTERNAL = partial(
    GitMaterial,
    url="git@github.com:edx/edx-internal.git",
    branch="master",
    polling=True,
    destination_directory="edx-internal",
    ignore_patterns=['**/*'],
)

EDGE_INTERNAL = partial(
    GitMaterial,
    url="git@github.com:edx/edge-internal.git",
    branch="master",
    polling=True,
    destination_directory="edge-internal",
    ignore_patterns=['**/*'],
)
