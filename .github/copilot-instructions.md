1. use the command "poetry run pytest" to run the tests
2. use the command "poetry run mypy" to check the type hints
3. use the command "poetry run flake8" to check the code style
4. generated tests should be placed in the "test" directory
5. tests that are written should never make network requests, tested code should be mocked
6. all flake8, mypy and pytest errors should be fixed automatically when introduced in new code
7. all function parameters and return values should have type hints
8. prefer typing constructs from the beartype.typing module
9. prefer | over Union for type hints
10. when changes are made to the code, ensure that the tests are updated accordingly
11. after all changes are complete run "poetry run flake8 && poetry run mypy && poetry run pytest" to validate. Fix any errors that arise.
12. use descriptive names for functions and variables
13. avoid using global variables, prefer passing parameters to functions
14. avoid using mutable default arguments in function definitions
15. ensure that all functions have docstrings explaining their purpose and usage
16. use f-strings for string formatting
17. avoid using print statements for debugging, use loguru instead
18. avoid imports inside functions, prefer placing them at the top of the file