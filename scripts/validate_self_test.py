#!/usr/bin/env python3
"""
Validate that self_test.py follows the core pipeline usage rules.

This script can be used in CI/CD to ensure self_test.py doesn't contain
duplicate code patterns.
"""

import sys
import subprocess
from pathlib import Path


def run_validation():
    """Run all validation checks for self_test.py."""
    print("Validating self_test.py compliance with core pipeline rules...")
    print()

    # Check if self_test.py exists
    self_test_path = Path("src/importer/self_test.py")
    if not self_test_path.exists():
        print("ERROR: self_test.py not found")
        return False

    print(f"SUCCESS: Found self_test.py at {self_test_path}")
    print()

    # Run the duplicate code detection
    print("Step 1: Checking for duplicate code patterns...")
    try:
        result = subprocess.run(["python3", "scripts/lint_self_test.py"],
                              capture_output=True, text=True, check=True)
        print("SUCCESS: No duplicate code patterns found")
    except subprocess.CalledProcessError as e:
        print("ERROR: Duplicate code patterns detected:")
        print(e.stdout)
        return False

    print()

    # Check for correct imports
    print("Step 2: Checking for correct CLI imports...")
    content = self_test_path.read_text()

    required_imports = [
        "from .cli import validate, apply",
        "# WARNING: ONLY use these CLI methods for validation/workflow!"
    ]

    missing_imports = []
    for required in required_imports:
        if required not in content:
            missing_imports.append(required)

    if missing_imports:
        print("ERROR: Missing required imports or comments:")
        for missing in missing_imports:
            print(f"   - {missing}")
        return False
    else:
        print("SUCCESS: Correct CLI imports found")

    print()

    # Check module docstring
    print("Step 3: Checking for module guidelines...")
    if "RULES FOR MAINTAINING THIS FILE" in content:
        print("SUCCESS: Module guidelines found")
    else:
        print("ERROR: Module guidelines not found in docstring")
        return False

    print()

    # Check for warning patterns
    print("Step 4: Checking for warning patterns...")
    warning_patterns = [
        "DO NOT add duplicate CSV parsing",
        "If tests fail, FIX THE CORE PIPELINE",
        "Tests real user workflow"
    ]

    missing_warnings = []
    for warning in warning_patterns:
        if warning not in content:
            missing_warnings.append(warning)

    if missing_warnings:
        print("ERROR: Missing warning patterns:")
        for missing in missing_warnings:
            print(f"   - {missing}")
        return False
    else:
        print("SUCCESS: All warning patterns found")

    print()
    print("SUCCESS: All validations passed! self_test.py follows core pipeline rules.")
    return True


if __name__ == "__main__":
    success = run_validation()
    sys.exit(0 if success else 1)