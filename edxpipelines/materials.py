"""
A set of standard overridable material definitions.
"""
import re
from functools import partial
from six.moves import urllib

from gomatic import GitMaterial


class InvalidGitRepoURL(Exception):
    """
    Raised when repo URL can't be parsed.
    """
    pass


class GomaticGitMaterial(GitMaterial):
    """
    Wrapper class around gomatic.gomatic.gocd.materials.GitMaterial in order to add helper methods.
    """
    # N.B. because of how GoCD implements equality comparison, this object cannot have
    # additional instance attributes and still compare equal to an equivalent GitMaterial.
    # It *has* to compare equal to GitMaterials, because gomatic reconstructs the GitMaterials
    # on the fly during ensure_materials.

    @property
    def org(self):
        clone_url = urllib.parse.urlparse(self.url).geturl()
        match = re.match(r'.*[:/](?P<org>[^/]*)/(?P<repo>[^/.]*)', clone_url)
        if not match:
            raise InvalidGitRepoURL(self.url)
        return match.group('org')

    @property
    def repo(self):
        clone_url = urllib.parse.urlparse(self.url).geturl()
        match = re.match(r'.*[:/](?P<org>[^/]*)/(?P<repo>[^/.]*)', clone_url)
        if not match:
            raise InvalidGitRepoURL(self.url)
        return match.group('repo')

    @property
    def envvar_name(self):
        """
        Return the material revision's GoCD environment variable name.
        """
        suffix = self.material_name if self.material_name else self.destination_directory
        return 'GO_REVISION_{suffix}'.format(suffix=suffix.replace('-', '_').upper())

    @property
    def envvar_bash(self):
        """
        Return the material revision's GoCD environment variable in de-referenced bash format.
        """
        return '${self.envvar_name}'.format(self=self)

    def __eq__(self, other):
        # N.B. GitMaterial is hard-coded, because otherwise the comparison GomaticGitMaterial(...) == GitMaterial(...)
        # won't work
        return isinstance(other, GitMaterial) and self.__dict__ == other.__dict__


def deployment_secure(deployment, branch='master', polling=True, destination_directory=None, ignore_patterns=None):
    """
    Initialize a GomaticGitMaterial representing a deployment's secure configuration repo.

    Args:
        deployment (str): Deployment for which to create the material (e.g., 'edx', 'edge')

    Returns:
        GomaticGitMaterial
    """
    return GomaticGitMaterial(
        url='git@github.com:edx-ops/{}-secure.git'.format(deployment),
        branch=branch,
        polling=polling,
        destination_directory=destination_directory or '{}-secure'.format(deployment),
        ignore_patterns=ignore_patterns or ['**/*'],
        shallow=True,
    )


def deployment_internal(deployment, branch='master', polling=True, destination_directory=None, ignore_patterns=None):
    """
    Initialize a GomaticGitMaterial representing a deployment's internal configuration repo.

    Args:
        deployment (str): Deployment for which to create the material (e.g., 'edx', 'edge')

    Returns:
        GomaticGitMaterial
    """
    return GomaticGitMaterial(
        url='git@github.com:edx/{}-internal.git'.format(deployment),
        branch=branch,
        polling=polling,
        destination_directory=destination_directory or '{}-internal'.format(deployment),
        ignore_patterns=ignore_patterns or ['**/*'],
        shallow=True,
    )


TUBULAR = partial(
    GomaticGitMaterial,
    url="https://github.com/edx/tubular",
    branch="master",
    polling=True,
    destination_directory="tubular",
    ignore_patterns=['**/*'],
    shallow=True,
)

CONFIGURATION = partial(
    GomaticGitMaterial,
    url="https://github.com/edx/configuration",
    branch="master",
    polling=True,
    destination_directory="configuration",
    ignore_patterns=['**/*'],
    shallow=True,
)

EDX_PLATFORM = partial(
    GomaticGitMaterial,
    url="https://github.com/edx/edx-platform",
    branch="release-candidate",
    polling=True,
    destination_directory="edx-platform",
    ignore_patterns=['**/*'],
    shallow=True,
)

EDX_SECURE = partial(deployment_secure, 'edx')

EDGE_SECURE = partial(deployment_secure, 'edge')

EDX_MICROSITE = partial(
    GomaticGitMaterial,
    url="git@github.com:edx/edx-microsite.git",
    branch="release",
    polling=True,
    destination_directory="edx-microsite",
    ignore_patterns=['**/*'],
    shallow=True,
)

EDX_INTERNAL = partial(deployment_internal, 'edx')

EDGE_INTERNAL = partial(deployment_internal, 'edge')

EDX_MKTG = partial(
    GomaticGitMaterial,
    url="git@github.com:edx/edx-mktg.git",
    branch="master",
    polling=True,
    destination_directory="edx-mktg",
    ignore_patterns=['**/*'],
)

ECOM_SECURE = partial(
    GomaticGitMaterial,
    url="git@github.com:edx-ops/ecom-secure",
    branch="master",
    polling=True,
    destination_directory="ecom-secure",
    ignore_patterns=['**/*'],
)

EDX_ORA2 = partial(
    GitMaterial,
    url='https://github.com/edx/edx-ora2',
    branch='master',
    polling=True,
    destination_directory='edx-ora2',
    ignore_patterns=['**/*']
)
