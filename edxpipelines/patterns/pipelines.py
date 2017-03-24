"""
Common gomatic pipeline patterns.

Responsibilities:
    Pipeline patterns should ...
        * expect ArtifactLocations as input.
            * It's the responsibility of the pipeline install script to ensure that the
              supplied artifacts don't refer to a job created by this pipeline.
        * not add PipelineMaterials (that should be handled by the pipeline-group script).
            * This allows pipeline pattern composition to be customized by pipeline groups.
        * return the pipeline that was created (or a list/namedtuple, if there were multiple pipelines).
"""
from gomatic import GitMaterial, PipelineMaterial

from edxpipelines import constants, materials
from edxpipelines.patterns import jobs, stages
from edxpipelines.patterns.authz import Permission, ensure_permissions
from edxpipelines.utils import ArtifactLocation


def generate_ami_deployment_pipeline(configurator,
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
            GitMaterial(
                "https://github.com/edx/tubular.git",
                polling=True,
                destination_directory="tubular",
                ignore_patterns=constants.MATERIAL_IGNORE_ALL_REGEX
            )
        )

    stages.generate_deploy_ami(pipeline,
                               asgard_api_endpoints,
                               asgard_token,
                               aws_access_key_id,
                               aws_secret_access_key,
                               manual_approval=True)
    return configurator


def build_edp_map(edp, pipeline_group, edp_map, build_pipeline=None, git_branch='master',
                  configuration_branch='master'):
    """
    Helper function for constructing the edp, pipeline, and storing the results
    in a map.  The edp and pipeline are returned.
    """
    pipeline = pipeline_group.ensure_replacement_of_pipeline(
        constants.DEPLOYMENT_PIPELINE_NAME_TPL(edp)
    )
    edp_map.append((edp, build_pipeline or pipeline, pipeline, git_branch, configuration_branch))
    return edp, pipeline


def generate_service_deployment_pipelines(
        configurator,
        config,
        base_edp,
        partial_app_material,
        has_migrations=True,
        has_edge=False,
):
    """
    Generates pipelines used to build and deploy a service to stage, loadtest,
    prod-edx, and prod-edge.

    Four pipelines are produced, named stage-edx-play, loadtest-edx-play, prod-edx-play,
    prod-edge-play. All three are placed in a group with the same name as the play.

    stage-edx-play polls a GitMaterial representing the service. When a change
    is detected on the master branch, it builds AMIs for stage and prod, deploys
    to stage, and gives pipeline operators the option of rolling back stage ASGs
    and migrations.

    prod-edx-play requires a PipelineMaterial representing the upstream
    stage-edx-play pipeline's build stage. When it completes successfully,
    prod-edx-play is armed. Deployment to prod is then manually approved
    by a pipeline operator. This pipeline gives operators the option of rolling
    back prod ASGs and migrations.

    loadtest-edx-play is independent of the stage-edx-play and prod-edx-play pipelines.
    It polls a GitMaterial representing the service. When a change is detected on the
    loadtest branch, it builds AMIs for loadtest, deploys to loadtest, and gives
    pipeline operators the option of rolling back loadtest ASGs and migrations.

    Args:
        configurator (gomatic.go_cd_configurator.GoCdConfigurator): GoCdConfigurator
            to use for building the pipeline.
        config (dict): Environment-independent config.
        env_configs (dict): Environment-specific config, keyed by environment.
        base_edp (edxpipelines.utils.EDP): Tuple indicating deployment and play for
            which to build a pipeline. The environment set in the tuple will be
            replaced depending on the pipeline being generated.
        partial_app_material (gomatic.gomatic.gocd.materials.GitMaterial): Partially
            applied (curried) material representing the source of the app to be
            deployed. The material's branch will be replaced depending on the pipeline
            being generated.
        has_migrations (bool): Whether to generate Gomatic for applying and
            rolling back migrations.
        has_edge (bool): Whether to generate service for deploying to prod-edge.
    """
    # Replace any existing pipeline group with a fresh one.
    configurator.ensure_removal_of_pipeline_group(base_edp.play)
    pipeline_group = configurator.ensure_pipeline_group(base_edp.play)

    # Create admin and operator roles to control pipeline group access.
    admin_role = '-'.join([base_edp.play, 'admin'])
    ensure_permissions(configurator, pipeline_group, Permission.ADMINS, [admin_role])

    operator_role = '-'.join([base_edp.play, 'operator'])
    ensure_permissions(configurator, pipeline_group, Permission.OPERATE, [operator_role])
    ensure_permissions(configurator, pipeline_group, Permission.VIEW, [operator_role])

    # Map EDPs to the pipelines that build their AMIs and the pipelines that deploy them.
    edp_pipeline_map = []

    # Create EDP and pipelines for each environment.
    stage_edp, stage_pipeline = build_edp_map(
        base_edp._replace(environment='stage', deployment='edx'),
        pipeline_group,
        edp_pipeline_map,
    )
    loadtest_edp, _pipeline = build_edp_map(
        base_edp._replace(environment='loadtest', deployment='edx'),
        pipeline_group,
        edp_pipeline_map,
        git_branch='loadtest',
        configuration_branch='-'.join(['loadtest', base_edp.play]),
    )
    auto_deploy = (stage_edp, loadtest_edp,)

    prod_deployments = ['edx']
    if has_edge:
        prod_deployments.append('edge')
    manual_deploy = ()
    for deployment in prod_deployments:
        prod_edp, _pipeline = build_edp_map(
            base_edp._replace(environment='prod', deployment=deployment),
            pipeline_group,
            edp_pipeline_map,
            build_pipeline=stage_pipeline,
        )
        manual_deploy += (prod_edp,)

    configuration_secure_material = materials.deployment_secure(
        'edx',
        destination_directory='configuration-secure'
    )
    configuration_internal_material = materials.deployment_internal(
        'edx',
        destination_directory='configuration-internal'
    )
    common_materials = [
        materials.TUBULAR(),
        configuration_secure_material,
        configuration_internal_material,
    ]

    for edp, build_pipeline, deploy_pipeline, git_branch, configuration_branch in edp_pipeline_map:
        configuration_material = materials.CONFIGURATION(branch=configuration_branch)
        app_material = partial_app_material(branch=git_branch)

        for material in common_materials + [configuration_material]:
            # All pipelines need access to tubular and configuration repos.
            deploy_pipeline.ensure_material(material)

        if edp in auto_deploy:
            # Most ensure_* methods are idempotent. ensure_material() seems
            # to be an exception: calling it repeatedly for the same pipeline
            # with the same materials results in duplicate materials.
            build_pipeline.ensure_material(app_material)
            build_pipeline.set_label_template(constants.DEPLOYMENT_PIPELINE_LABEL_TPL(app_material))
        else:
            # The prod pipeline only requires successful completion of the stage
            # pipeline's AMI build stage, from which it will retrieve an AMI artifact.
            deploy_pipeline.ensure_material(
                PipelineMaterial(
                    build_pipeline.name,
                    constants.BUILD_AMI_STAGE_NAME,
                    material_name=build_pipeline.name
                )
            )

            # Pipelines return their label when referenced by name. We share the
            # label set for the stage pipeline with the prod pipeline.
            deploy_pipeline.set_label_template('${{{}}}'.format(build_pipeline.name))

            # The prod pipeline's first stage is a no-op 'armed stage' that will
            # be followed by a deploy stage requiring manual approval.
            stages.generate_armed_stage(deploy_pipeline, constants.ARMED_STAGE_NAME)

        app_version_var = '$GO_REVISION_{}'.format(app_material.material_name.upper())
        overrides = {
            'app_version': app_version_var,
            '{}_VERSION'.format(base_edp.play.upper()): app_version_var,
        }

        build_stage = build_pipeline.ensure_stage(constants.BUILD_AMI_STAGE_NAME)
        jobs.generate_build_ami(
            build_stage,
            edp,
            app_material.url,
            configuration_secure_material,
            configuration_internal_material,
            constants.PLAYBOOK_PATH_TPL(edp),
            config[edp],
            version_tags={
                edp.play: (app_material.url, app_version_var),
                'configuration': (configuration_material.url, configuration_material.envvar_bash),
                'configuration_secure': (
                    configuration_secure_material.url, constants.CONFIGURATION_SECURE_VERSION
                ),
                'configuration_internal': (
                    configuration_internal_material.url, constants.CONFIGURATION_INTERNAL_VERSION
                ),
            },
            **overrides
        )

        # The next stage in all three pipelines deploys an AMI built in an upstream stage.
        deploy_stage = deploy_pipeline.ensure_stage(constants.DEPLOY_AMI_STAGE_NAME)

        if edp in manual_deploy:
            # We don't want the prod pipeline to deploy automatically (yet).
            deploy_stage.set_has_manual_approval()

        ami_artifact_location = ArtifactLocation(
            build_pipeline.name,
            constants.BUILD_AMI_STAGE_NAME,
            constants.BUILD_AMI_JOB_NAME_TPL(edp),
            constants.BUILD_AMI_FILENAME
        )
        jobs.generate_deploy_ami(
            deploy_stage,
            ami_artifact_location,
            edp,
            config[edp],
            has_migrations=has_migrations
        )

        # The next stage in the pipeline rolls back the ASG/AMI deployed by the
        # upstream deploy stage.
        rollback_asgs_stage = deploy_pipeline.ensure_stage(constants.ROLLBACK_ASGS_STAGE_NAME)

        # Rollback stages always require manual approval from the operator.
        rollback_asgs_stage.set_has_manual_approval()

        deployment_artifact_location = ArtifactLocation(
            deploy_pipeline.name,
            constants.DEPLOY_AMI_STAGE_NAME,
            constants.DEPLOY_AMI_JOB_NAME,
            constants.DEPLOY_AMI_OUT_FILENAME
        )
        jobs.generate_rollback_asgs(rollback_asgs_stage, deployment_artifact_location, config)

        if has_migrations:
            # If the service has migrations, add an additional stage for rolling
            # back any migrations applied by the upstream deploy stage.
            rollback_migrations_stage = deploy_pipeline.ensure_stage(constants.ROLLBACK_MIGRATIONS_STAGE_NAME)

            # Rollback stages always require manual approval from the operator.
            rollback_migrations_stage.set_has_manual_approval()

            migration_info_location = ArtifactLocation(
                deploy_pipeline.name,
                constants.DEPLOY_AMI_STAGE_NAME,
                constants.DEPLOY_AMI_JOB_NAME,
                constants.MIGRATION_OUTPUT_DIR_NAME,
                is_dir=True
            )
            jobs.generate_rollback_migrations(
                rollback_migrations_stage,
                edp.play,
                edp.play,
                '/edx/app/{}'.format(edp.play),
                constants.DB_MIGRATION_USER,
                config[edp]['db_migration_pass'],
                migration_info_location,
                ami_artifact_location=ami_artifact_location,
                config=config[edp],
            )
