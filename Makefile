.PHONY: help requirements test_requirements test

test:
	tox

test.%:
	tox -- --script edxpipelines/pipelines/$*.py

diff:
	env SAVE_CONFIG=true tox

diff.%:
	env SAVE_CONFIG=true tox -- --script edxpipelines/pipelines/$*.py

quality:
	pep8 --config=.pep8 edxpipelines

requirements:
	pip install -r requirements.txt

test_requirements: requirements
	pip install -r requirements/test_requirements.txt
