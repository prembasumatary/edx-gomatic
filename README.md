# edx-pipelines go here

## How to reverse-engineer a pipline
```
python -m reverse_engineer --ssl -s <server_address> -p <pipeline_name> --username <username> --password <password> > new_script.py
```

## How to push a pipeline to gocd:
```
python edxpipelines/pipelines/deploy_ami.py --variable_file ../gocd-pipelines/gocd/vars/tools/deploy_edge_ami.yml --variable_file ../gocd-pipelines/gocd/vars/tools/tools.yml
```

You can also do a dry run of the script:
```
python edxpipelines/pipelines/deploy_ami.py --dry-run --variable_file ../gocd-pipelines/gocd/vars/tools/deploy_edge_ami.yml --variable_file ../gocd-pipelines/gocd/vars/tools/tools.yml
```

This will output 2 files:
- config-after.xml
- config-before.xml

You can then diff these files:
```
diff config-before.xml config-after.xml
```

## Things to look out for
- Currently any *Secure Variables* must be hashed first by the gocd server before putting them in the script
- gocd tends to mangle long strings or strings that have carrage returns in them.
- If you need to view a secure variable in the terminal use ```printf "%s" $ENV_VAR``` as echo will not work.
