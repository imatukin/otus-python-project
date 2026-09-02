test:
	poetry run pytest

lint:
	poetry run pylint $(shell git ls-files '*.py')

