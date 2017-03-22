"""
Task patterns for private releases.
"""

from gomatic import BuildArtifact

from .common import tubular_task, generate_target_directory
from ... import constants


def generate_create_private_release_candidate(
        job, git_token, source_repo, source_base_branch, source_branch, target_repo,
        target_base_branch, target_branch, target_reference_repo=None,
):
    """
    Add a task that creates a new release-candidate by merging a set of approved
    PRs in the target repo.

    Arguments:
        job: The gomatic.Job to add this task to
        git_token: The token to authenticate with github
        source_repo: A tuple of (user, repo) specifying the repository to
            base the new branch from.
        source_base_branch: A branch name. Any PRs in target_repo that have
            been merged into this branch will be excluded.
        source_branch: A branch name. This is the branch that the PRs
            will be merged onto.
        target_repo: A tuple of (user, repo) specifying the repository to
            merge PRs from.
        target_base_branch: A branch name. This is the branch that PRs must target
            in order to be included in the merge.
        target_branch: A branch name. This is the branch that will be created by the
            merge (and will be force-pushed into target_repo).
        target_reference_repo: A path to an existing local checkout of the target_repo
            that can be used to speed up fresh clones.
    """
    # Gomatic forgot to expose ensure_unencrypted_secure_environment_variables,
    # so we have to reach behind the mangled name to get it ourselves.
    thing_with_environment_variables = job._Job__thing_with_environment_variables  # pylint: disable=protected-access
    thing_with_environment_variables.ensure_unencrypted_secure_environment_variables({
        'GIT_TOKEN': git_token,
    })

    job.ensure_environment_variables({
        'GIT_AUTHOR_NAME': 'edx-pipeline-bot',
        'GIT_AUTHOR_EMAIL': 'admin+edx-pipeline-bot@edx.org',
        'GIT_COMMITTER_NAME': 'edx-pipeline-bot',
        'GIT_COMMITTER_EMAIL': 'admin+edx-pipeline-bot@edx.org',
    })

    generate_target_directory(job)

    artifact_path = '{}/{}'.format(
        constants.ARTIFACT_PATH,
        constants.PRIVATE_RC_FILENAME
    )

    args = [
        '--token', '$GIT_TOKEN',
        '--target-repo', target_repo[0], target_repo[1],
        '--target-base-branch', target_base_branch,
        '--source-repo', source_repo[0], source_repo[1],
        '--source-base-branch', source_base_branch,
        '--target-branch', target_branch,
        '--source-branch', source_branch,
        '--out-file', artifact_path,
        '--sha-variable', 'edx-platform-version',
        '--repo-variable', 'edx-platform-repo',
    ]

    if target_reference_repo:
        args.extend(['--target-reference-repo', target_reference_repo])

    job.ensure_task(tubular_task(
        'merge-approved-prs',
        args,
        working_dir=None
    ))

    job.ensure_artifacts(set([BuildArtifact(artifact_path)]))
