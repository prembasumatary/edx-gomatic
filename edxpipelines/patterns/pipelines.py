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
        configuration_secure_repo=config['configuration_secure_repo'],
        aws_access_key_id=config['aws_access_key_id'],
        aws_secret_access_key=config['aws_secret_access_key'],
        hipchat_token=hipchat_token,
        hipchat_room=hipchat_room,
        configuration_secure_version='$GO_REVISION_CONFIGURATION_SECURE',
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


def generate_service_deployment_pipelines(configurator, config, env_configs, base_edp, partial_app_material):
    """
    Generates pipelines used to build and deploy a service to stage, prod, and
    loadtest environments. The generated pipelines only support a single deployment
    (e.g., edx, edge).

    Three pipelines are produced, named stage-deployment-play, prod-deployment-play,
    and loadtest-deployment-play. All three are placed in a group with the same name
    as the play.

    stage-deployment-play polls a GitMaterial representing the service. When a change
    is detected on the master branch, it builds AMIs for stage and prod, deploys
    to stage, and gives pipeline operators the option of rolling back stage ASGs
    and migrations.

    prod-deployment-play requires a PipelineMaterial representing the upstream
    stage-deployment-play pipeline's build stage. When it completes successfully,
    prod-deployment-play is armed. Deployment to prod is then manually approved
    by a pipeline operator. This pipeline gives operators the option of rolling
    back prod ASGs and migrations.

    loadtest-deployment-play is independent of the stage-deployment-play and
    prod-deployment-play pipelines. It polls a GitMaterial representing the service.
    When a change is detected on the loadtest branch, it builds AMIs for loadtest,
    deploys to loadtest, and gives pipeline operators the option of rolling back
    loadtest ASGs and migrations.

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

    # Create tuples representing each EDP.
    stage_edp = base_edp._replace(environment='stage')
    prod_edp = base_edp._replace(environment='prod')
    loadtest_edp = base_edp._replace(environment='loadtest')

    # Create pipelines for each environment.
    stage_pipeline = pipeline_group.ensure_replacement_of_pipeline(
        constants.DEPLOYMENT_PIPELINE_NAME_TPL(stage_edp)
    )
    prod_pipeline = pipeline_group.ensure_replacement_of_pipeline(
        constants.DEPLOYMENT_PIPELINE_NAME_TPL(prod_edp)
    )
    loadtest_pipeline = pipeline_group.ensure_replacement_of_pipeline(
        constants.DEPLOYMENT_PIPELINE_NAME_TPL(loadtest_edp)
    )

    # Map pipelines to their EDPs. This is useful later on when we need to find
    # an EDP given a pipeline.
    pipeline_edp_map = {
        stage_pipeline: stage_edp,
        prod_pipeline: prod_edp,
        loadtest_pipeline: loadtest_edp,
    }

    # Ensure materials for each pipeline.
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
        materials.CONFIGURATION(),
        configuration_secure_material,
        configuration_internal_material,
    ]

    # The stage and prod pipelines share most materials. The only difference
    # material-wise is the app material branch they poll for changes.
    for pipeline in (stage_pipeline, loadtest_pipeline):
        for material in common_materials:
            pipeline.ensure_material(material)

    # master_app_material = partial_app_material(branch='master')
    master_app_material = partial_app_material(branch='renzo/pipeline-test')
    stage_pipeline.ensure_material(master_app_material)
    stage_pipeline.set_label_template(constants.DEPLOYMENT_PIPELINE_LABEL_TPL(master_app_material))

    # loadtest_app_material = partial_app_material(branch='loadtest')
    loadtest_app_material = partial_app_material(branch='renzo/pipeline-loadtest')
    loadtest_pipeline.ensure_material(loadtest_app_material)
    loadtest_pipeline.set_label_template(constants.DEPLOYMENT_PIPELINE_LABEL_TPL(loadtest_app_material))

    # The prod pipeline only requires successful completion of the stage pipeline's
    # AMI build stage, from which it will retrieve an AMI artifact.
    prod_pipeline.ensure_material(
        PipelineMaterial(
            stage_pipeline.name,
            constants.BUILD_AMI_STAGE_NAME,
            material_name=stage_pipeline.name
        )
    )

    # Pipelines return their label when referenced by name. We share the label
    # set for the stage pipeline with the prod pipeline.
    prod_pipeline.set_label_template('${{{}}}'.format(stage_pipeline.name))

    # Create each pipeline's first stage. For the stage and loadtest pipelines,
    # this is the AMI build stage.
    stage_build_stage = stage_pipeline.ensure_stage(constants.BUILD_AMI_STAGE_NAME)
    loadtest_build_stage = loadtest_pipeline.ensure_stage(constants.BUILD_AMI_STAGE_NAME)

    app_version_var = '$GO_REVISION_{}'.format(master_app_material.material_name.upper())
    overrides = {
        'app_version': app_version_var,
        '{}_VERSION'.format(base_edp.play.upper()): app_version_var,
    }

    # Map EDPs to the stages that build their AMIs.
    build_stage_map = {
        stage_edp: stage_build_stage,
        prod_edp: stage_build_stage,
        loadtest_edp: loadtest_build_stage,
    }

    for edp, stage in build_stage_map.items():
        jobs.generate_build_ami(
            stage,
            edp,
            master_app_material.url,
            configuration_secure_material,
            configuration_internal_material,
            constants.PLAYBOOK_PATH_TPL(edp),
            env_configs[edp.environment],
            **overrides
        )

    # The prod pipeline's first stage is a no-op 'armed stage' that will be
    # followed by a deploy stage requiring manual approval.
    stages.generate_armed_stage(prod_pipeline, constants.ARMED_STAGE_NAME)

    # The next stage in all three pipelines deploys an AMI built in an upstream stage.
    stage_deploy_stage = stage_pipeline.ensure_stage(constants.DEPLOY_AMI_STAGE_NAME)
    prod_deploy_stage = prod_pipeline.ensure_stage(constants.DEPLOY_AMI_STAGE_NAME)
    loadtest_deploy_stage = loadtest_pipeline.ensure_stage(constants.DEPLOY_AMI_STAGE_NAME)

    # We don't want the prod pipeline to deploy automatically (yet).
    prod_deploy_stage.set_has_manual_approval()

    # Map deploy stages to the pipelines which contain their AMI artifacts.
    ami_source_map = [
        (stage_edp, stage_deploy_stage, stage_pipeline),
        (prod_edp, prod_deploy_stage, stage_pipeline),
        (loadtest_edp, loadtest_deploy_stage, loadtest_pipeline),
    ]

    for edp, stage, source_pipeline in ami_source_map:
        ami_artifact_location = ArtifactLocation(
            source_pipeline.name,
            constants.BUILD_AMI_STAGE_NAME,
            constants.BUILD_AMI_JOB_NAME_TPL(edp),
            constants.BUILD_AMI_FILENAME
        )

        jobs.generate_deploy_ami(stage, ami_artifact_location, edp, env_configs[edp.environment])

    # The final two stages in each pipeline roll back the ASG/AMI deployed and
    # any migrations applied by the upstream deploy stage.
    for pipeline, edp in pipeline_edp_map.items():
        rollback_asgs_stage = pipeline.ensure_stage(constants.ROLLBACK_ASGS_STAGE_NAME)
        rollback_migrations_stage = pipeline.ensure_stage(constants.ROLLBACK_MIGRATIONS_STAGE_NAME)

        # Rollback stages always require manual approval from the operator.
        rollback_asgs_stage.set_has_manual_approval()
        rollback_migrations_stage.set_has_manual_approval()

        deployment_artifact_location = ArtifactLocation(
            pipeline.name,
            constants.DEPLOY_AMI_STAGE_NAME,
            constants.DEPLOY_AMI_JOB_NAME,
            constants.DEPLOY_AMI_OUT_FILENAME
        )
        jobs.generate_rollback_asgs(rollback_asgs_stage, deployment_artifact_location, config)

        inventory_location = ArtifactLocation(
            constants.DEPLOYMENT_PIPELINE_NAME_TPL(edp),
            constants.DEPLOY_AMI_STAGE_NAME,
            constants.DEPLOY_AMI_JOB_NAME,
            constants.ANSIBLE_INVENTORY_FILENAME
        )
        instance_key_location = ArtifactLocation(
            constants.DEPLOYMENT_PIPELINE_NAME_TPL(edp),
            constants.DEPLOY_AMI_STAGE_NAME,
            constants.DEPLOY_AMI_JOB_NAME,
            constants.KEY_PEM_FILENAME
        )
        migration_info_location = ArtifactLocation(
            constants.DEPLOYMENT_PIPELINE_NAME_TPL(edp),
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
            env_configs[edp.environment]['db_migration_pass'],
            inventory_location,
            instance_key_location,
            migration_info_location,
        )
