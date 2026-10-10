# Tests for the drift lookup and the command line report.
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from ignoredrift import cli
from ignoredrift.core import find_drift, repo_root, tracked_files, untrack_commands


# Shared fixture: a throwaway repository on disk.
class RepoCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ignore-drift-")
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        self.git("init", "-q", ".")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git(self, *args):
        proc = subprocess.run(
            ["git", "-C", self.repo] + list(args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            raise AssertionError(proc.stderr.decode("utf-8", "replace"))
        return proc.stdout.decode("utf-8", "replace")

    def write(self, rel, text):
        path = os.path.join(self.repo, rel)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text)

    # Commit files first and add the ignore file afterwards, which is the
    # mistake this tool reports on.
    def seed(self, files, ignore_text):
        for rel, text in files.items():
            self.write(rel, text)
        self.git("add", "-A")
        self.write(".gitignore", ignore_text)
        self.git("add", ".gitignore")
        self.git(
            "-c", "user.name=t", "-c", "user.email=t@example.com",
            "commit", "-qm", "seed",
        )


class CoreTests(RepoCase):
    def test_clean_repo_reports_nothing(self):
        self.seed({"src/app.py": "print(1)\n"}, "*.log\n__pycache__/\n")
        self.assertEqual(find_drift(self.repo), [])

    def test_tracked_file_matching_rule_is_reported(self):
        self.seed({"build.log": "noise\n", "keep.txt": "ok\n"}, "*.log\n")
        drift = find_drift(self.repo)
        self.assertEqual([d.path for d in drift], ["build.log"])
        self.assertEqual(drift[0].rule, "*.log")
        self.assertEqual(drift[0].source, ".gitignore")
        self.assertEqual(drift[0].line, 1)

    def test_directory_rule_covers_nested_file(self):
        self.seed({"secrets/key.txt": "hunter2\n"}, "secrets/\n\n*.log\n")
        drift = find_drift(self.repo)
        self.assertEqual([d.path for d in drift], ["secrets/key.txt"])
        self.assertEqual(drift[0].rule, "secrets/")

    def test_negated_pattern_is_not_drift(self):
        self.seed({"keep.log": "ok\n"}, "*.log\n!keep.log\n")
        self.assertEqual(find_drift(self.repo), [])

    def test_pattern_reincluded_after_a_negation_is_drift(self):
        self.seed({"keep.log": "ok\n"}, "*.log\n!keep.log\nkeep.log\n")
        drift = find_drift(self.repo)
        self.assertEqual([d.path for d in drift], ["keep.log"])
        self.assertEqual(drift[0].rule, "keep.log")
        self.assertEqual(drift[0].line, 3)

    def test_untrack_commands_quote_awkward_paths(self):
        self.seed({"my file.log": "x\n", "build.log": "y\n"}, "*.log\n")
        drift = find_drift(self.repo)
        commands = untrack_commands(drift)
        self.assertIn("git rm --cached -- build.log", commands)
        self.assertIn("git rm --cached -- 'my file.log'", commands)

    def test_repo_root_accepts_a_subdirectory(self):
        self.seed({"src/app.py": "print(1)\n"}, "*.log\n")
        found = repo_root(os.path.join(self.repo, "src"))
        self.assertEqual(os.path.realpath(found), os.path.realpath(self.repo))
        self.assertIn("src/app.py", tracked_files(self.repo))


class CliTests(RepoCase):
    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_json_report_and_exit_code(self):
        self.seed({"build.log": "noise\n"}, "*.log\n")
        code, out, _ = self.run_cli([self.repo, "--json"])
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["drift"][0]["path"], "build.log")
        self.assertEqual(payload["drift"][0]["rule"], "*.log")

    def test_clean_repo_exits_zero_and_quiet_silences_it(self):
        self.seed({"src/app.py": "print(1)\n"}, "*.log\n")
        code, out, _ = self.run_cli([self.repo])
        self.assertEqual(code, 0)
        self.assertIn("no drift", out)
        code, out, _ = self.run_cli([self.repo, "--quiet"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_fix_flag_prints_untrack_commands(self):
        self.seed({"secrets/key.txt": "hunter2\n"}, "secrets/\n")
        code, out, _ = self.run_cli([self.repo, "--fix"])
        self.assertEqual(code, 1)
        self.assertIn("git rm --cached -- secrets/key.txt", out)

    def test_exit_zero_flag_suppresses_failure(self):
        self.seed({"build.log": "noise\n"}, "*.log\n")
        code, _, _ = self.run_cli([self.repo, "--exit-zero"])
        self.assertEqual(code, 0)

    def test_outside_a_repository_is_an_error(self):
        plain = os.path.join(self.tmp, "plain")
        os.makedirs(plain)
        code, _, err = self.run_cli([plain])
        self.assertEqual(code, 2)
        self.assertIn("ignore-drift:", err)


if __name__ == "__main__":
    unittest.main()
