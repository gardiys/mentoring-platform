import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from check_tests import SMOKE_TESTS, backend_quick_tests, components, main, run_check


class GitCheckTests(unittest.TestCase):
    def test_frontend_only_commit_does_not_select_backend(self):
        self.assertEqual(components(["frontend/src/app/App.tsx"]), {"frontend"})
        self.assertEqual(components(["README.md"]), set())
        self.assertEqual(components(["backend/app/main.py"]), {"backend"})
        self.assertEqual(components(["Makefile"]), {"backend", "frontend"})

    def test_large_refactor_caps_extra_modules_and_reports_deferred_tests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / "backend/tests"
            tests.mkdir(parents=True)
            files = []
            for index in range(10):
                (tests / f"test_feature_{index}.py").touch()
                files.append(f"backend/tests/test_feature_{index}.py")
            modules, deferred = backend_quick_tests(files, root)
        self.assertEqual(modules[: len(SMOKE_TESTS)], list(SMOKE_TESTS))
        self.assertEqual(len(modules), len(SMOKE_TESTS) + 3)
        self.assertEqual(deferred, 7)

    def test_missing_or_deleted_test_file_is_not_passed_to_pytest(self):
        with tempfile.TemporaryDirectory() as directory:
            modules, deferred = backend_quick_tests(
                ["backend/tests/test_deleted.py"], Path(directory)
            )
        self.assertEqual(modules, list(SMOKE_TESTS))
        self.assertEqual(deferred, 0)

    def test_child_failure_is_propagated_and_output_is_saved(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            result = run_check(
                [sys.executable, "-c", "print('test failed'); raise SystemExit(7)"],
                root,
                root / "tests.log",
                5,
                terminal_output=False,
            )
            self.assertEqual(result, 7)
            self.assertIn("test failed", (root / "tests.log").read_text())

    def test_deleted_backend_file_also_selects_backend_for_a_frontend_commit(self):
        with (
            patch("sys.argv", ["check_tests", "quick", "frontend/src/app/App.tsx"]),
            patch("check_tests.subprocess.check_output", return_value=b"backend/app/removed.py\0"),
            patch("check_tests.run_check", return_value=0) as run,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(main(), 0)
        self.assertEqual(
            [call.args[1].name for call in run.call_args_list], ["backend", "frontend"]
        )

    def test_hanging_child_is_stopped_at_the_deadline(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            result = run_check(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                root,
                root / "tests.log",
                0.1,
                terminal_output=False,
            )
            self.assertEqual(result, 124)
            self.assertIn("stopping process group", (root / "tests.log").read_text())


if __name__ == "__main__":
    unittest.main()
