# Architected and built by classy+.
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent


class InstallerEntrypointTests(unittest.TestCase):
    def test_sidelab_launcher_exists_and_delegates_to_run_bat(self):
        launcher = ROOT / "SIDELAB.bat"

        self.assertTrue(launcher.exists(), "SIDELAB.bat should exist as the one-click launcher")

        content = launcher.read_text(encoding="utf-8")
        self.assertIn("call \"%~dp0run.bat\"", content)

    def test_install_guide_points_users_to_sidelab_launcher(self):
        guide = (ROOT / "README-INSTALL.md").read_text(encoding="utf-8")

        self.assertIn("double-click `SIDELAB.bat`", guide)
        self.assertIn("`SIDELAB.bat`", guide)


if __name__ == "__main__":
    unittest.main()
