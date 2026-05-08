
import sys
import os

# Add src to path
sys.path.append(os.getcwd())

from src.search_module import SearchModule
from src.config import default_config

def test_abbreviation():
    # Mock database and logger
    class MockDB:
        def fetch_one(self, *args, **kwargs): return None
        def fetch_all(self, *args, **kwargs): return []
        def update_company(self, *args, **kwargs): pass
        def get_company(self, *args, **kwargs): return None

    class MockLogger:
        def log_step_start(self, *args, **kwargs): return "log_id"
        def log_step_end(self, *args, **kwargs): pass
        def log_event(self, *args, **kwargs): pass

    sm = SearchModule(db=MockDB(), pipeline_logger=MockLogger(), config=default_config)

    test_cases = [
        ("ABC Software Co., Ltd", "ABC"),
        ("FPT Software", "FPT"),
        ("Hòa Phát Group Joint Stock", "HPG"),
        ("Vietnam Dairy Products", "DP"),
        ("A", None),
    ]

    for name, expected in test_cases:
        actual = sm._compute_abbreviation(name)
        print(f"Input: '{name}' | Expected: '{expected}' | Actual: '{actual}'")
        assert actual == expected, f"Failed for {name}: expected {expected}, got {actual}"

    print("\nAll test cases passed!")

if __name__ == "__main__":
    try:
        test_abbreviation()
    except AssertionError as e:
        print(f"\nAssertion failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        sys.exit(1)
