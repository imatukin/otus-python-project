# Список всех подключённых remote и текущая ветка — вычисляются при запуске make
REMOTES := $(shell git remote)
BRANCH := $(shell git rev-parse --abbrev-ref HEAD)

.PHONY: test lint coverage pull push pushtags

test:
	poetry run pytest

lint:
	poetry run pylint $(shell git ls-files '*.py')

coverage:
	poetry run pytest -s --cov --cov-report html --cov-fail-under=95

# Забрать изменения со всех remote: сначала общий fetch, затем fast-forward
# текущей ветки от каждого из них по очереди
pull:
	git fetch --all --prune
	@for remote in $(REMOTES); do \
		echo "==> pull $$remote/$(BRANCH)"; \
		git pull --ff-only $$remote $(BRANCH) || exit 1; \
	done

# Отправить текущую ветку во все remote
push:
	@for remote in $(REMOTES); do \
		echo "==> push $$remote/$(BRANCH)"; \
		git push $$remote $(BRANCH) || exit 1; \
	done

# Отправить все локальные теги во все remote
pushtags:
	@for remote in $(REMOTES); do \
		echo "==> push tags -> $$remote"; \
		git push $$remote --tags || exit 1; \
	done
