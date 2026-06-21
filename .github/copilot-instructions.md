1. use the command "poetry run pytest" to run the tests
2. use the command "poetry run mypy" to check the type hints
3. use the command "poetry run ruff check ." to check linting and import order
4. use the command "poetry run ruff format ." to fix whitespace or formatting issues (and "poetry run ruff format --check ." to verify)
5. generated tests should be placed in the "test" directory
6. tests that are written should never make network requests, tested code should be mocked
7. all ruff, mypy and pytest errors should be fixed automatically when introduced in new code
8. all function parameters and return values should have type hints
9. prefer typing constructs from the beartype.typing module
10. when changes are made to the code, ensure that the tests are updated accordingly
11. when adding tests, only start fixing ruff or mypy errors in tests after all tests are passing, unless they are causing the tests to fail
12. after all changes are complete run "poetry run ruff check . && poetry run ruff format --check . && poetry run mypy" to validate structure. Fix any errors that arise.
13. use descriptive names for functions and variables
14. avoid using global variables, prefer passing parameters to functions
15. avoid using mutable default arguments in function definitions
16. ensure that all functions have docstrings explaining their purpose and usage
17. use f-strings for string formatting
18. avoid using print statements for debugging, use loguru instead
19. avoid imports inside functions, prefer placing them at the top of the file
20. ensure no blank lines contain any whitespace
21. ensure there is no whitespace at the end of lines
22. Use PySide6 (Qt6) instead of PyQt5 or other Qt bindings
23. Follow Qt best practices for widget creation and layout management
24. Include proper signal-slot connections where appropriate
25. Use modern Python type hints
26. Create clean, modular widget classes that can be easily tested
27. Include proper error handling for GUI operations
28. Use Qt's resource system when dealing with images or icons
29. Follow Qt styling conventions and use Qt Style Sheets (QSS) when needed
30. Do not disable linting or type checking in the code unless the user agrees to it