#!/usr/bin/env python
import sys
from os import path

# Used to import edxpipelines files - since the module is not installed.
sys.path.append(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))

from edxpipelines.pipelines.script import pipeline_script


def install_pipelines(configurator, config, env_configs):
    """
    Generates 2 pipelines used to deploy the discovery service to stage and prod.

    The first pipeline contains 2 stages, run serially:

        1. Build AMIs. Contains 2 jobs, run in parallel.

            a. Build stage AMI. Contains 5 tasks, run serially:
                i.   Select base AMI.
                ii.  Launch a new instance on which we will build an AMI.
                iii. Run the Ansible play for the service.
                iv.  Create a stage AMI based on the instance.
                v.   Regardless of job state: clean up instance.

            b. Build prod AMI. Contains 5 tasks, run serially:
                i.   Select base AMI.
                ii.  Launch a new instance on which we will build an AMI.
                iii. Run the Ansible play for the service.
                iv.  Create a prod AMI based on the instance.
                v.   Regardless of job state: clean up instance.

        2. Migrate and deploy to stage. Contains 1 job.

            a. Migrate and deploy to stage. Contains 4+ tasks, run serially:
                i.   Launch instance of stage AMI built in the previous stage.
                ii.  Run migrations against stage.
                iii. Any post-migration tasks (e.g., running management commands).
                iv.  Deploy the stage AMI.
                v.   Regardless of job state: clean up instance.

    The second pipeline contains 4 stages, run serially:

        1. Armed stage. Triggered by success of the last stage in the preceding pipeline.

        2. Migrate and deploy to prod. Requires manual execution. Contains 1 job.

            a. Migrate and deploy to prod. Contains 4+ tasks, run serially:
                i.   Launch instance of prod AMI built in the previous pipeline.
                ii.  Run migrations against prod.
                iii. Any post-migration tasks (e.g., running management commands).
                iv.  Deploy the prod AMI.
                v.   Regardless of job state: clean up instance.

        3. Roll back prod ASGs (code). Requires manual execution.

        4. Roll back prod migrations.
    """
    pass


if __name__ == '__main__':
    pipeline_script(install_pipelines)
