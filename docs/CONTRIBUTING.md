# Contributing to BlueCat CSV Importer

Thank you for contributing to the BlueCat CSV Importer project! This guide will help you understand how to contribute effectively.

## IMPORTANT: Self-Test Development Guidelines

### CRITICAL: Self-Test Rules

The `src/importer/self_test.py` file has **strict rules** to prevent code duplication:

#### WHAT YOU MUST DO:
1. **ALWAYS** use `CLI.validate()` for CSV validation tests
2. **ALWAYS** use `CLI.apply()` for workflow tests
3. **ALWAYS** import from core modules: `from .cli import validate, apply`
4. **ALWAYS** fix core pipeline issues when self-test fails

#### WHAT YOU MUST NEVER DO:
1. **NEVER** implement custom CSV parsing logic
2. **NEVER** call `CSVParser()` directly (except for simple row counting)
3. **NEVER** call `parser.parse()` for validation
4. **NEVER** duplicate validation logic from core modules
5. **NEVER** add "workarounds" in self-test to fix failing tests

#### WHEN TESTS FAIL:

**WRONG WAY:**
```python
# WRONG: Don't do this!
def _test_csv_validation(self, client, test_config):
    # Custom parsing logic - this creates duplicate code!
    parser = CSVParser(csv_path)
    rows = parser.parse(strict=True)
    # More custom validation...
```

**RIGHT WAY:**
```python
# CORRECT: Do this instead!
def _test_csv_validation(self, client, test_config):
    # Use core pipeline - tests real user workflow!
    validate(csv_file=csv_path, strict=True)
```

If `CLI.validate()` or `CLI.apply()` fails, **fix the core modules**:
- Fix issues in `src/importer/cli.py`
- Fix issues in `src/importer/core/parser.py`
- Fix issues in `src/importer/validation/safety.py`
- Do NOT modify self-test to work around core issues

### Automated Protection

We have multiple safeguards to prevent duplicate code:

1. **Pre-commit hooks** that block duplicate patterns
2. **Linting script** at `scripts/lint_self_test.py`
3. **Documentation warnings** in the module docstring
4. **Code review guidelines** below

## Development Workflow

### 1. Setup Development Environment

```bash
# Clone the repository
git clone <repo-url>
cd bluecat-csv

# Install dependencies
poetry install
poetry shell

# Install pre-commit hooks
pre-commit install

# Run tests
pytest
```

### 2. Make Changes

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Make your changes following the coding standards
3. Run tests and linting: `make check`
4. Commit changes: `git commit -m "feat: add new feature"`
5. Push and create pull request

### 3. Code Standards

#### Type Hints (MANDATORY)
```python
# Good
def resolve_path(path: str, resource_type: str) -> int:
    ...

# Bad - missing type hints
def resolve_path(path, resource_type):
    ...
```

#### Documentation
```python
def compute_diff(desired: ResourceState, current: ResourceState) -> Operation:
    """Compute the operation needed to reconcile desired and current state.

    Args:
        desired: The desired resource state from CSV
        current: The current resource state from BAM

    Returns:
        Operation: The operation to perform (CREATE/UPDATE/DELETE/NOOP)

    Raises:
        ValidationError: If state comparison fails
    """
```

#### Error Handling
```python
from .utils.exceptions import ResourceNotFoundError

if not resource:
    logger.error("resource_not_found", path=path, resource_type=resource_type)
    raise ResourceNotFoundError(f"Resource not found: {path}")
```

### 4. Testing

#### Run All Tests
```bash
pytest -v
pytest --cov=src/importer --cov-report=term-missing
```

#### Run Specific Tests
```bash
pytest tests/unit/test_parser.py -v
pytest tests/integration/ -v
```

#### Self-Test Testing
```bash
# Test self-test linting rules
python3 scripts/lint_self_test.py

# Run self-test (requires BAM connection)
python3 import.py self-test --config config.yaml
```

## Review Process

When reviewing pull requests, pay special attention to:

### Self-Test Changes (CRITICAL)
1. **Check for duplicate code patterns**:
   - Any `CSVParser()` instantiations
   - Any `parser.parse()` calls
   - Any custom validation logic
2. **Ensure CLI methods are used**:
   - `validate()` for CSV validation
   - `apply()` for workflow tests
3. **Reject workarounds**: If tests fail, fix core modules

### General Code Review Checklist
- [ ] All functions have type hints
- [ ] All public functions have docstrings
- [ ] Code is formatted with `black`
- [ ] Code passes `ruff` linting
- [ ] Code passes `mypy` type checking
- [ ] Tests are added for new functionality
- [ ] Self-test rules are followed (if applicable)

## Quick Reference: Self-Test Anti-Patterns

| Anti-Pattern | Correct Approach | What to Avoid |
|-------------|-------------------|------------------|
| CSV Validation | `validate(csv_path, strict=True)` | `CSVParser(csv_path).parse()` |
| Workflow Tests | `apply(csv_path, dry_run=True)` | Custom workflow logic |
| Error Handling | Fix core modules | Add workarounds in self-test |
| Import Strategy | `from .cli import validate, apply` | Copy core logic to self-test |

## Getting Help

If you're unsure about self-test guidelines:

1. **Check the module docstring** in `src/importer/self_test.py`
2. **Run the linting script**: `python3 scripts/lint_self_test.py`
3. **Ask for clarification** in your pull request
4. **Review existing self-test methods** for correct patterns

## Goal

The self-test should be a **validation of the real user pipeline**, not a separate implementation. When a user runs `bluecat-import apply file.csv`, they're using the same code that self-test validates.

This ensures:
- Tests validate real user experience
- Core pipeline improvements benefit self-test automatically
- No code duplication or divergence
- Single source of truth for validation logic

---

Thank you for following these guidelines! Your contributions help maintain code quality and prevent technical debt.