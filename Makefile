.DEFAULT_GOAL := quality

.PHONY: requirements quality

requirements:
	pip install -r requirements.txt

test-requirements:
	pip install -r requirements/test_requirements.txt

quality: test-requirements
	pep8 --config=.pep8 edxpipelines
