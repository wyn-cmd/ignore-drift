# ignore-drift

ignore-drift reports files that git still tracks even though a `.gitignore` rule matches them. That combination is always a mistake, and it is the quiet way secrets, build output and editor junk end up in a repository forever: someone commits a file, adds an ignore rule later, and git keeps versioning the file because it is already in the index.

The tool asks git itself, so pattern negation, `**` globs, nested `.gitignore` files, `.git/info/exclude` and `core.excludesFile` are all handled exactly as git handles them. Nothing is reimplemented.

## Why the obvious check does not work

Running `git check-ignore` on a tracked path prints nothing by default, because git deliberately skips paths that are already in the index. Adding `--no-index` makes git evaluate the rules for those paths too, which is what turns a hidden situation into a visible one. ignore-drift does that for every tracked file in one pass and reports the exact rule that matched, with its source file and line number.

## Install

No dependencies beyond git and Python 3.8 or newer.

```
pip install .
```

Or run it straight from a checkout without installing anything:

```
python3 -m ignoredrift /path/to/repo
```

## Usage

```
ignore-drift [path] [--json] [--fix] [--quiet] [--exit-zero] [--version]
```

- `path` is any path inside the repository to inspect, and it defaults to the current directory.
- `--json` prints a machine readable report with the repository root, a count and one record per file (`path`, `rule`, `source`, `line`).
- `--fix` prints the `git rm --cached` commands that would untrack the reported files. It never runs them.
- `--quiet` prints nothing when the repository is clean.
- `--exit-zero` always exits 0, for reporting jobs that should not fail a build.
- `--version` prints the version.

Exit codes are 0 when no tracked file matches an ignore rule, 1 when at least one does, and 2 when git fails or the path is not inside a working tree. That makes the tool usable as a pre-commit hook or a CI step with no wrapper script.

## Example

```
$ ignore-drift
2 tracked files match an ignore rule in /home/me/project

  build.log
    matched *.log from .gitignore line 4
  secrets/key.txt
    matched secrets/ from .gitignore line 2

git keeps versioning tracked files even when a rule matches them, so a secret or build artifact committed before the rule existed stays in the repository. Untrack each file with git rm --cached and commit the change.

$ ignore-drift --fix
...
commands:
  git rm --cached -- build.log
  git rm --cached -- secrets/key.txt
```

JSON output for the same repository:

```
$ ignore-drift --json
{
  "repo": "/home/me/project",
  "count": 2,
  "drift": [
    {"path": "build.log", "rule": "*.log", "source": ".gitignore", "line": 4},
    {"path": "secrets/key.txt", "rule": "secrets/", "source": ".gitignore", "line": 2}
  ]
}
```

## Tests

The test suite builds throwaway repositories in temporary directories and covers a clean repository, a tracked file caught by a glob rule, a directory rule covering a nested file, a negated pattern that must not be reported, paths that need shell quoting, and the exit codes and JSON shape of the command line. Run it with:

```
python3 -m unittest discover -s tests -v
```

## Limits

- Untracking a file with `git rm --cached` stops future commits from tracking it, but the file and its history stay in the repository. Anything sensitive needs the history rewritten as well, and the file itself should be rotated.
- Submodule gitlinks and symlinks appear in `git ls-files` output like any other path and are reported the same way.
- The tool reads the index, so it reports the state of the working tree you point it at, not of a remote branch.

## License

MIT. See LICENSE.
