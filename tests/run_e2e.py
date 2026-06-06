#!/usr/bin/env python3
import os
import sys
import unittest

# Ensure project root is in path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

def main():
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=os.path.dirname(__file__), pattern='test_*.py')
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Calculate detailed summary
    total = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    skips = len(result.skipped)
    passes = total - failures - errors - skips
    
    print("\n" + "=" * 50)
    print("FIFA World Cup 2026 E2E Test Suite Summary")
    print("=" * 50)
    print(f"Total Tests Run: {total}")
    print(f"Passes:          {passes}")
    print(f"Skips:           {skips}")
    print(f"Failures:        {failures}")
    print(f"Errors:          {errors}")
    print("=" * 50)
    
    if failures > 0 or errors > 0:
        print("RESULT: FAILED")
        sys.exit(1)
    else:
        print("RESULT: SUCCESS")
        sys.exit(0)

if __name__ == '__main__':
    main()
