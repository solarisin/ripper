---
trigger: model_decision
description: after changes reqested are complete
---

- verify all tests still pass
  - if any tests fail, fix them

- after all tests are passing again
  - execute flake8 and mypy with their default project configuration
    - if either produce errors, fix them

