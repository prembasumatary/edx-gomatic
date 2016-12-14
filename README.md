# GoMatic scripts for edX pipelines
This repository contains Python 2.7+ code which uses the Gomatic Python module to create pipelines and their stages, jobs, and tasks in GoCD. [Gomatic](https://github.com/SpringerSBM/gomatic) is a domain-specific language (DSL) which allows pipelines to be created via code under source control instead of via the GoCD web GUI. 

## How to reverse-engineer a pipeline
```
python -m reverse_engineer --ssl -s <server_address> -p <pipeline_name> --username <username> --password <password> > new_script.py
```

## How to push a pipeline to gocd:
```
python edxpipelines/pipelines/deploy_ami.py --variable_file ../gocd-pipelines/gocd/vars/tools/deploy_edge_ami.yml --variable_file ../gocd-pipelines/gocd/vars/tools/tools.yml
```

For testing purposes, you can also perform a dry run of the script:
```
python edxpipelines/pipelines/deploy_ami.py --dry-run --variable_file ../gocd-pipelines/gocd/vars/tools/deploy_edge_ami.yml --variable_file ../gocd-pipelines/gocd/vars/tools/tools.yml
```

The dry run will output 2 files:
- config-after.xml
- config-before.xml

You can then diff these files:
```
diff config-before.xml config-after.xml
```

## Cautions and Caveats
- Currently any *Secure Variables* must be hashed first by the GoCD server before putting them in the script
- GoCD tends to mangle long strings or strings that have carrage returns in them.
