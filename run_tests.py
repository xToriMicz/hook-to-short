"""Run all Hook-to-Short test suites."""
import sys
import importlib

suites = [
    "test_classify_url",
    "test_gui_feedback",
    "test_tier2",
]

all_passed = True
for name in suites:
    print(f"\n{'='*50}")
    print(f"  {name}")
    print(f"{'='*50}\n")
    mod = importlib.import_module(name)
    if not mod.run_tests():
        all_passed = False

print(f"\n{'='*50}")
if all_passed:
    print("ALL SUITES PASSED")
else:
    print("SOME SUITES FAILED")
sys.exit(0 if all_passed else 1)
