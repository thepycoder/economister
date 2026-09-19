#!/usr/bin/env python3
"""Test runner for all Economist EPUB Generator tests.

This module discovers and runs all tests in the src directory.

Usage:
    python test.py                    # Run all tests
    python test.py -v                  # Verbose output
    python test.py TestClassName       # Run specific test class
    python test.py module_test         # Run specific test module
"""

import sys
import unittest
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent))


def run_all_tests(verbosity=2, pattern='*_test.py'):
    """Run all tests in the src directory.

    Args:
        verbosity: Output verbosity level (0=quiet, 1=normal, 2=verbose)
        pattern: Pattern to match test files

    Returns:
        TestResult object
    """
    # Discover all tests
    loader = unittest.TestLoader()
    start_dir = Path(__file__).parent
    suite = loader.discover(start_dir, pattern=pattern)

    # Run tests
    runner = unittest.TextTestRunner(verbosity=verbosity)
    return runner.run(suite)


def run_specific_tests(test_name, verbosity=2):
    """Run specific test module or class.

    Args:
        test_name: Name of test module or class to run
        verbosity: Output verbosity level

    Returns:
        TestResult object
    """
    loader = unittest.TestLoader()
    start_dir = Path(__file__).parent

    # Package path: belgium / belgium.models_test
    if test_name == 'belgium' or test_name.startswith('belgium.'):
        suite = loader.discover(
            str(start_dir / 'belgium'),
            pattern='*_test.py',
            top_level_dir=str(start_dir),
        )
        if test_name.startswith('belgium.') and test_name != 'belgium':
            # Narrow to one module if possible.
            module_name = test_name
            if not module_name.endswith('_test'):
                module_name = module_name + '_test'
            try:
                suite = loader.loadTestsFromName(module_name)
            except Exception:
                pass
        runner = unittest.TextTestRunner(verbosity=verbosity)
        return runner.run(suite)

    # Try to load as module first
    try:
        if not test_name.endswith('_test'):
            test_name = test_name.replace('.py', '') + '_test'
        suite = loader.loadTestsFromName(test_name)
    except Exception:
        # Try to load as test class
        suite = unittest.TestSuite()
        for module in start_dir.glob('*_test.py'):
            module_name = module.stem
            try:
                test_module = __import__(module_name)
                if hasattr(test_module, test_name):
                    suite.addTests(loader.loadTestsFromTestCase(
                        getattr(test_module, test_name)
                    ))
            except Exception:
                continue

    runner = unittest.TextTestRunner(verbosity=verbosity)
    return runner.run(suite)


def print_test_summary(result):
    """Print summary of test results.

    Args:
        result: TestResult object
    """
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    total = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    skipped = len(result.skipped) if hasattr(result, 'skipped') else 0

    print(f"Total tests run: {total}")
    print(f"Successes: {total - failures - errors - skipped}")

    if failures:
        print(f"Failures: {failures}")
        for test, traceback in result.failures:
            print(f"  - {test}")

    if errors:
        print(f"Errors: {errors}")
        for test, traceback in result.errors:
            print(f"  - {test}")

    if skipped:
        print(f"Skipped: {skipped}")

    print("=" * 70)

    if result.wasSuccessful():
        print("✅ ALL TESTS PASSED!")
    else:
        print("❌ SOME TESTS FAILED")
        sys.exit(1)


def list_available_tests():
    """List all available test modules and classes."""
    print("\nAvailable test modules:")
    print("-" * 30)

    for test_file in sorted(Path(__file__).parent.glob('*_test.py')):
        module_name = test_file.stem
        print(f"  {module_name}")

        # Try to list test classes in module
        try:
            test_module = __import__(module_name)
            classes = [name for name in dir(test_module)
                      if name.startswith('Test')]
            if classes:
                for class_name in classes:
                    print(f"    - {class_name}")
        except:
            pass

    print("\nUsage examples:")
    print("  python test.py                    # Run all tests")
    print("  python test.py models_test        # Run models tests")
    print("  python test.py TestArticle        # Run specific test class")


def main():
    """Main entry point for test runner."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Run tests for Economist EPUB Generator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s                     # Run all tests
  %(prog)s -v                  # Verbose output
  %(prog)s -q                  # Quiet output
  %(prog)s models_test         # Run specific test module
  %(prog)s TestArticle         # Run specific test class
  %(prog)s --list              # List available tests
        '''
    )

    parser.add_argument(
        'test',
        nargs='?',
        help='Specific test module or class to run'
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_const',
        const=2,
        default=1,
        dest='verbosity',
        help='Verbose test output'
    )

    parser.add_argument(
        '-q', '--quiet',
        action='store_const',
        const=0,
        dest='verbosity',
        help='Quiet test output'
    )

    parser.add_argument(
        '--list',
        action='store_true',
        help='List available test modules and classes'
    )

    parser.add_argument(
        '--failfast',
        action='store_true',
        help='Stop on first failure'
    )

    args = parser.parse_args()

    if args.list:
        list_available_tests()
        return

    print("\n" + "=" * 70)
    print("ECONOMIST EPUB GENERATOR - TEST SUITE")
    print("=" * 70)

    if args.test:
        print(f"\nRunning specific tests: {args.test}")
        result = run_specific_tests(args.test, args.verbosity)
    else:
        print("\nRunning all tests...")
        result = run_all_tests(args.verbosity)

    print_test_summary(result)


if __name__ == '__main__':
    main()
