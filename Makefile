.PHONY: help requirements test_requirements test

test:
	tox

test.%:
	tox -- --script edxpipelines/pipelines/$*.py

diff:
	tox -- --save-config

diff.%:
	tox -- --script edxpipelines/pipelines/$*.py --save-config

quality:
	pep8 --config=.pep8 edxpipelines

requirements:
	pip install -r requirements.txt

test_requirements: requirements
	pip install -r requirements/test_requirements.txt

validate:
	pytest -k test_scripts