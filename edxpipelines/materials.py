from gomatic import GitMaterial


TUBULAR = GitMaterial(
    url="https://github.com/edx/tubular",
    branch="master",
    material_name="tubular",
    polling=True,
    destination_directory="tubular",
    ignore_patterns=['**/*'],
)

CONFIGURATION = GitMaterial(
    url="https://github.com/edx/configuration",
    branch="master",
    material_name="configuration",
    polling=True,
    destination_directory="configuration",
    ignore_patterns=['**/*'],
)

EDX_PLATFORM = GitMaterial(
    url="https://github.com/edx/edx-platform",
    branch="release-candidate",
    material_name="edx-platform",
    polling=True,
    destination_directory="edx-platform",
    ignore_patterns=['**/*'],
)

EDX_SECURE = GitMaterial(
    url="git@github.com:edx-ops/edx-secure.git",
    branch="master",
    material_name="edx-secure",
    polling=True,
    destination_directory="edx-secure",
    ignore_patterns=['**/*'],
)

EDGE_SECURE = GitMaterial(
    url="git@github.com:edx-ops/edge-secure.git",
    branch="master",
    material_name="edge-secure",
    polling=True,
    destination_directory="edge-secure",
    ignore_patterns=['**/*'],
)

MCKINSEY_SECURE = GitMaterial(
    url="git@github.com:edx-ops/mckinsey-secure.git",
    branch="master",
    material_name="mckinsey-secure",
    polling=True,
    destination_directory="mckinsey-secure",
    ignore_patterns=['**/*'],
)

EDX_MICROSITE = GitMaterial(
    url="git@github.com:edx/edx-microsite.git",
    branch="release",
    material_name="edx-microsite",
    polling=True,
    destination_directory="edx-microsite",
    ignore_patterns=['**/*'],
)

EDX_INTERNAL = GitMaterial(
    url="git@github.com:edx/edx-internal.git",
    branch="master",
    material_name="edx-internal",
    polling=True,
    destination_directory="edx-internal",
    ignore_patterns=['**/*'],
)

EDGE_INTERNAL = GitMaterial(
    url="git@github.com:edx/edge-internal.git",
    branch="master",
    material_name="edge-internal",
    polling=True,
    destination_directory="edge-internal",
    ignore_patterns=['**/*'],
)

MCKINSEY_INTERNAL = GitMaterial(
    url="git@github.com:mckinseyacademy/mckinsey-internal.git",
    branch="master",
    material_name="mckinsey-internal",
    polling=True,
    destination_directory="mckinsey-internal",
    ignore_patterns=['**/*'],
)
