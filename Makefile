.PHONY: help requirements test_requirements test

test:
	tox

dryrun:
	tox -- --live -k test_script

dryrun.%:
	tox -- --live -k test_script -k $*

diff:
	tox -e dryrun -- --save-config

diff.%:
	tox -e dryrun -- --script edxpipelines/pipelines/$*.py --save-config

requirements:
	pip install -r requirements.txt

test_requirements: requirements
	pip install -r requirements/test_requirements.txt

deadcode:
	tox -e deadcode
