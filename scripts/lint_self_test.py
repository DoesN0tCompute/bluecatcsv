#!/usr/bin/env python3
"""
Linting rule to prevent duplicate CSV parsing/validation logic in self_test.py

This script detects when self_test.py contains duplicate patterns that should
use the core CLI methods instead.
"""

import ast
import sys
from pathlib import Path


class DuplicateCodeDetector(ast.NodeVisitor):
    """Detect duplicate CSV parsing and validation patterns in self-test."""

    def __init__(self):
        self.issues = []
        self.current_class = None
        self.current_method = None

    def visit_ClassDef(self, node):
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = None

    def visit_FunctionDef(self, node):
        self.current_method = node.name
        self.generic_visit(node)
        self.current_method = None

    def visit_Call(self, node):
        # Check for direct CSVParser instantiation (should use CLI.validate)
        if isinstance(node.func, ast.Name) and node.func.id == "CSVParser":
            self.issues.append({
                "line": node.lineno,
                "type": "direct_csv_parser",
                "message": "Direct CSVParser() usage found. Use CLI.validate() instead",
                "method": self.current_method
            })

        # Check for direct parser.parse() calls (should use CLI.validate)
        if (isinstance(node.func, ast.Attribute) and
            node.func.attr == "parse" and
            isinstance(node.func.value, ast.Name) and
            "parser" in node.func.value.id.lower()):
            self.issues.append({
                "line": node.lineno,
                "type": "direct_parse_call",
                "message": "Direct parser.parse() usage found. Use CLI.validate() instead",
                "method": self.current_method
            })

        # Check for check_csv_for_dangerous_operations calls (CLI.apply handles this)
        if (isinstance(node.func, ast.Name) and
            node.func.id == "check_csv_for_dangerous_operations"):
            self.issues.append({
                "line": node.lineno,
                "type": "direct_safety_check",
                "message": "Direct safety check found. CLI.apply() handles this automatically",
                "method": self.current_method
            })

        self.generic_visit(node)


def check_self_test_duplicates():
    """Check self_test.py for duplicate code patterns."""
    # Find self_test.py relative to project root
    project_root = Path(__file__).parent.parent
    self_test_path = project_root / "src" / "importer" / "self_test.py"

    if not self_test_path.exists():
        print(f"ERROR: self_test.py not found at {self_test_path}")
        return False

    with open(self_test_path, 'r') as f:
        content = f.read()
        tree = ast.parse(content)

    detector = DuplicateCodeDetector()
    detector.visit(tree)

    if detector.issues:
        print(f"FAILED: Found {len(detector.issues)} potential duplicate code issues in self_test.py:")
        print()

        for issue in detector.issues:
            print(f"  WARNING: Line {issue['line']} in {issue['method']}(): {issue['message']}")

        print()
        print("TO FIX THESE ISSUES:")
        print("   1. Replace CSVParser() calls with CLI.validate()")
        print("   2. Replace parser.parse() calls with CLI.validate()")
        print("   3. Remove check_csv_for_dangerous_operations() calls (CLI.apply() handles it)")
        print("   4. If validation fails, fix core modules, not self_test.py")
        print()
        print("NOTE: See the module docstring in self_test.py for guidelines")

        return False
    else:
        print("SUCCESS: No duplicate code patterns found in self_test.py")
        return True


if __name__ == "__main__":
    success = check_self_test_duplicates()
    sys.exit(0 if success else 1)