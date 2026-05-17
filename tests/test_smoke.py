"""Smoke tests for the application package."""

import unittest

from oncall_app import __version__


class SmokeTest(unittest.TestCase):
    """Basic package-level checks."""

    def test_package_has_version(self):
        """The package exposes the expected local version."""
        self.assertEqual(__version__, "0.1.0")


if __name__ == "__main__":
    unittest.main()
