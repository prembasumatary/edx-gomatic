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

from edxpipelines import constants, materials, utils
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


# TODO: this can be deleted!
def generate_basic_multistage_pipeline(
        configurator,
        play,
        pipeline_group,
        playbook_path,
        app_repo,
        service_name,
        hipchat_room,
        config,
        post_migration_stages=(),
        skip_migrations=False,
        **kwargs
):
    """
    DEPRECATED. Use generate_service_deployment_pipelines().

    This pattern generates a pipeline that is suitable for the majority of edX's independently-deployable applications
    (IDAs).

    The generated pipeline will includes stages that do the following:

        1. Launch a new instance on which we will build an AMI.
        2. Run the Ansible play for the service.
        3. Create an AMI based on the instance.
        4. Run migrations.
        5. Deploy the AMI (after manual intervention)
        6. Destroy the instance on which the AMI was built.

    Notes:
        The instance launched/destroyed is NEVER inserted into the load balancer or serving user requests.
    """
    edp = utils.EDP(config['edx_environment'], config['edx_deployment'], play)

    application_name = service_name
    application_path = '/edx/app/' + service_name
    application_user = service_name
    hipchat_token = config['hipchat_token']

    pipeline = configurator.ensure_pipeline_group(pipeline_group) \
        .ensure_replacement_of_pipeline('-'.join(edp)) \
        .ensure_material(GitMaterial(config['tubular_url'],
                                     branch=config.get('tubular_version', 'master'),
                                     polling=True,
                                     destination_directory='tubular',
                                     ignore_patterns=constants.MATERIAL_IGNORE_ALL_REGEX)) \
        .ensure_material(GitMaterial(config['configuration_url'],
                                     branch=config.get('configuration_version', 'master'),
                                     polling=True,
                                     destination_directory='configuration',
                                     ignore_patterns=constants.MATERIAL_IGNORE_ALL_REGEX)) \
        .ensure_material(GitMaterial(config['app_repo'],
                                     branch=config.get('app_version', 'master'),
                                     material_name=play,
                                     polling=True,
                                     destination_directory=config['app_destination_directory'])) \
        .ensure_material(GitMaterial(config['configuration_secure_repo'],
                                     branch=config.get('configuration_secure_version', 'master'),
                                     material_name='configuration_secure',
                                     polling=True,
                                     destination_directory=constants.PRIVATE_CONFIGURATION_LOCAL_DIR,
                                     ignore_patterns=constants.MATERIAL_IGNORE_ALL_REGEX)) \
        .ensure_material(GitMaterial(config['configuration_internal_repo'],
                                     branch=config.get('configuration_internal_version', 'master'),
                                     material_name='configuration_internal',
                                     polling=True,
                                     destination_directory=constants.INTERNAL_CONFIGURATION_LOCAL_DIR,
                                     ignore_patterns=constants.MATERIAL_IGNORE_ALL_REGEX)) \
        .ensure_environment_variables({
            'APPLICATION_USER': application_user,
            'APPLICATION_NAME': application_name,
            'APPLICATION_PATH': application_path,
        })

    ami_selection_stage = stages.generate_base_ami_selection(
        pipeline,
        config['aws_access_key_id'],
        config['aws_secret_access_key'],
        edp=edp,
        manual_approval=not config.get('auto_run', False),
    )

    # The artifact that provides the AMI-ID to launch
    ami_artifact = utils.ArtifactLocation(
        pipeline.name,
        ami_selection_stage.name,
        constants.BASE_AMI_SELECTION_JOB_NAME,
        constants.BASE_AMI_OVERRIDE_FILENAME,
    )

    # Launch a new instance on which to build the AMI
    stages.generate_launch_instance(
        pipeline,
        config['aws_access_key_id'],
        config['aws_secret_access_key'],
        config['ec2_vpc_subnet_id'],
        config['ec2_security_group_id'],
        config['ec2_instance_profile_name'],
        config['base_ami_id'],
        base_ami_id_artifact=ami_artifact
    )

    # Run the Ansible play for the service
    stages.generate_run_play(
        pipeline,
        playbook_with_path=playbook_path,
        edp=edp,
        app_repo=app_repo,
        configuration_secure_repo=config['configuration_secure_repo'],
        configuration_secure_dir=constants.PRIVATE_CONFIGURATION_LOCAL_DIR,
        # remove above line and uncomment the below once materials are changed over to list.
        # configuration_secure_dir='{}-secure'.format(config['edx_deployment']),
        private_github_key=config['github_private_key'],
        hipchat_token=hipchat_token,
        hipchat_room=hipchat_room,
        disable_edx_services='true',
        COMMON_TAG_EC2_INSTANCE='true',
        **kwargs
    )

    # Create an AMI
    stages.generate_create_ami_from_instance(
        pipeline,
        edp=edp,
        app_repo=app_repo,
        aws_access_key_id=config['aws_access_key_id'],
        aws_secret_access_key=config['aws_secret_access_key'],
        hipchat_token=hipchat_token,
        hipchat_room=hipchat_room,
        version_tags={
            'configuration': (config['configuration_url'], '$GO_REVISION_CONFIGURATION'),
            'configuration_secure': (config['configuration_secure_repo'], '$GO_REVISION_CONFIGURATION_SECURE'),
        },
        # remove above line and uncomment the below once materials are changed over to list.
        # configuration_secure_version='$GO_REVISION_{}_SECURE'.format(config['edx_deployment'].upper()),
        **kwargs
    )

    # Run database migrations
    ansible_inventory_location = utils.ArtifactLocation(
        pipeline.name,
        constants.LAUNCH_INSTANCE_STAGE_NAME,
        constants.LAUNCH_INSTANCE_JOB_NAME,
        constants.ANSIBLE_INVENTORY_FILENAME
    )
    instance_ssh_key_location = utils.ArtifactLocation(
        pipeline.name,
        constants.LAUNCH_INSTANCE_STAGE_NAME,
        constants.LAUNCH_INSTANCE_JOB_NAME,
        constants.KEY_PEM_FILENAME
    )
    launch_info_location = utils.ArtifactLocation(
        pipeline.name,
        constants.LAUNCH_INSTANCE_STAGE_NAME,
        constants.LAUNCH_INSTANCE_JOB_NAME,
        constants.LAUNCH_INSTANCE_FILENAME
    )

    if not skip_migrations:
        stages.generate_run_migrations(
            pipeline,
            config['db_migration_pass'],
            ansible_inventory_location,
            instance_ssh_key_location,
            launch_info_location,
            application_user=application_user,
            application_name=application_name,
            application_path=application_path
        )

    # Run post-migration stages/tasks
    for stage in post_migration_stages:
        stage(
            pipeline,
            ansible_inventory_location,
            instance_ssh_key_location,
            launch_info_location,
            application_user=application_user,
            application_name=application_name,
            application_path=application_path,
            hipchat_token=hipchat_token,
            hipchat_room=hipchat_room
        )

    # Deploy the AMI (after user manually approves)
    ami_file_location = utils.ArtifactLocation(
        pipeline.name,
        constants.BUILD_AMI_STAGE_NAME,
        constants.BUILD_AMI_JOB_NAME,
        'ami.yml'
    )
    stages.generate_deploy_ami(
        pipeline,
        config['asgard_api_endpoints'],
        config['asgard_token'],
        config['aws_access_key_id'],
        config['aws_secret_access_key'],
        ami_file_location,
        manual_approval=not config.get('auto_deploy_ami', False)
    )

    # Terminate the instance used to create the AMI and run migrations. It was never inserted into the
    # load balancer, or serving requests, so this is safe.
    instance_info_location = utils.ArtifactLocation(
        pipeline.name,
        constants.LAUNCH_INSTANCE_STAGE_NAME,
        constants.LAUNCH_INSTANCE_JOB_NAME,
        constants.LAUNCH_INSTANCE_FILENAME
    )
    stages.generate_terminate_instance(
        pipeline,
        instance_info_location,
        aws_access_key_id=config['aws_access_key_id'],
        aws_secret_access_key=config['aws_secret_access_key'],
        hipchat_token=hipchat_token,
        runif='any'
    )


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
        env_config (dict): Environment-specific config, keyed by environment.
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
    auto_deploy = (stage_edp,loadtest_edp,)

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
        base_edp.deployment,
        destination_directory='configuration-secure'
    )
    configuration_internal_material = materials.deployment_internal(
        base_edp.deployment,
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
