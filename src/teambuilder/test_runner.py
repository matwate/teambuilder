import unittest
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    suite = unittest.defaultTestLoader.discover(str(project_root), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
