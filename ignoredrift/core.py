# Shared plumbing for the checks: thin wrappers over git plus the drift lookup.
import subprocess
from dataclasses import dataclass


class GitError(RuntimeError):
    pass


# One tracked file that an ignore rule says should not be tracked.
@dataclass(frozen=True)
class Drift:
    path: str
    rule: str
    source: str
    line: int


# Run git inside a repo and hand back raw stdout.
# check-ignore exits 1 when nothing matched, which is a normal result here, so
# anything above 1 is treated as a real failure and raised.
def _git(repo, args, stdin=None):
    proc = subprocess.run(
        ["git", "-C", repo] + list(args),
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode > 1:
        message = proc.stderr.decode("utf-8", "replace").strip()
        raise GitError("git %s failed: %s" % (" ".join(args), message))
    return proc.stdout


# Resolve the top level of the working tree that contains the given path.
def repo_root(path):
    out = _git(path, ["rev-parse", "--show-toplevel"])
    root = out.decode("utf-8", "replace").strip()
    if not root:
        raise GitError("%s is not inside a git working tree" % path)
    return root


# Every path git currently records in the index, as repo relative strings.
def tracked_files(repo):
    raw = _git(repo, ["ls-files", "-z"])
    return [p for p in raw.decode("utf-8", "replace").split("\0") if p]


# Ask git which of the given paths its ignore rules would refuse.
# The --no-index flag matters: without it git skips tracked paths, which are
# exactly the paths this tool exists to report on.
def matched_rules(repo, paths):
    if not paths:
        return {}
    stdin = "\0".join(paths).encode("utf-8")
    raw = _git(
        repo,
        ["check-ignore", "--stdin", "-z", "-v", "--no-index"],
        stdin=stdin,
    )
    fields = [f for f in raw.decode("utf-8", "replace").split("\0") if f != ""]
    matches = {}
    # Verbose NUL output is four fields per hit: source, line, pattern, path.
    # git reports the rule that decided the path, and a rule starting with !
    # means the path survives the ignore file, so those hits are dropped.
    for i in range(0, len(fields) - 3, 4):
        source, line, pattern, path = fields[i : i + 4]
        if pattern.startswith("!"):
            continue
        try:
            line_number = int(line)
        except ValueError:
            line_number = 0
        matches[path] = (pattern, source, line_number)
    return matches


# The full answer for a repo: tracked files that still match an ignore rule.
def find_drift(repo):
    tracked = tracked_files(repo)
    matches = matched_rules(repo, tracked)
    drift = []
    for path, (pattern, source, line) in matches.items():
        drift.append(Drift(path=path, rule=pattern, source=source, line=line))
    drift.sort(key=lambda d: d.path)
    return drift


# The commands a human would run to untrack the offending files.
def untrack_commands(drift):
    return ["git rm --cached -- %s" % _quote(d.path) for d in drift]


# Quote a path for a shell line only when it needs it.
def _quote(path):
    if path and all(c.isalnum() or c in "-_./@" for c in path):
        return path
    return "'" + path.replace("'", "'\\''") + "'"
