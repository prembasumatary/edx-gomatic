"""
Gomatic task patterns.

Responsibilities:
    Task patterns should ...
        * ``ensure`` the environment variables that they need to use.
            * This hides the implementation of how values are being passed to scripts from callers.
        * use ``ensure_task`` if the task only needs to be run once.
        * expect file paths as input (and produce files at well-documented paths).
            * Because you can't fetch an artifact from a stage that's in progress, tasks
              should assume that artifacts that they need will already have been fetched
              by one of the higher-up constructs.
        * return the generated task (if there was only one), or a list of tasks, if there are multiple
          (or, for extra credit, a namedtuple, so that the tasks can be named).
        * use constants for all folder/filenames that are known in advance (rather than
          being arguments to the pattern).
        * ``ensure`` the scm materials needed for the task to function.
"""
# Provide backward compatible
from .common import *  # pylint: disable=wildcard-import
