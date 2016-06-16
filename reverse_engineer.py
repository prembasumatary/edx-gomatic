import sys
from gomatic import go_cd_configurator

# patch the as_python method to generate the python we would like to use
def as_python(self, pipeline, with_save=True):
    head = "#!/usr/bin/env python\n\n" \
             "from gomatic import *\n\n" \
             "import click\n" \
             "import edxpipelines.utils as utils\n\n\n"

    head += "@click.command()\n"\
           "@click.option('--save-config', 'save_config_locally', envvar='SAVE_CONFIG', help='Save the pipeline configuration xml locally', required=False, default=False)\n"\
           "@click.option('--dry-run', envvar='DRY_RUN', help='do a dry run of  the pipeline installation, and save the pre/post xml configurations locally', required=False, default=True)\n"\
           "@click.option('--variable_file', 'variable_files', multiple=True, help='path to yaml variable file with a dictionary of key/value pairs to be used as variables in the script', required=False)\n"\
           "@click.option('-e', '--variable', 'cmd_line_vars', multiple=True, help='key/value of a variable used as a replacement in this script', required=False, type=(str, str), nargs=2)\n"\
           "def install_pipeline(save_config_locally=False, dry_run=False, variable_files=[], cmd_line_vars={}):\n"

    result = "config = utils.merge_files_and_dicts(variable_files, cmd_line_vars)\n\n"
    result += "configurator = " + str(self) + "\n"
    result += "pipeline = configurator"
    result += pipeline.as_python_commands_applied_to_server()
    if with_save:
        result += "\n\nconfigurator.save_updated_config(save_config_locally=save_config_locally, dry_run=dry_run)"

    final_result = ""
    for line in result.splitlines():
        final_result += '{line: >{width}}\n'.format(line=line, width=len(line) + 4)  # +4 to add the indent
    return head + final_result

# patch the new formatting
go_cd_configurator.GoCdConfigurator.as_python = as_python

#call the main
go_cd_configurator.main(sys.argv[1:])



