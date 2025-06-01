---
trigger: model_decision
description: when executing terminal commands
---

- when executing pytest
  - use 'poetry run pytest' to execute all tests using the pytest project configuration defined in pyproject.toml
  - use 'poetry run pytest [args]' to execute pytest with custom args

- when executing flake8
  - use 'poetry run flake8' to execute flake8 using the project configuration defined in pyproject.toml
  - use 'poetry run flake8 [args]' to execute flake8 with custom args

- when executing mypy
  - use 'poetry run mypy' to execute mypy using the project configuration defined in pyproject.toml
  - use 'poetry run mypy [args]' to execute mypy with custom args

- when installing new packages
  - use 'poetry add [package]' to install a new package

- when executing other python commands
  - use 'poetry run python [args]' 