# Command line entry point for ignore-drift.
import argparse
import json
import os
import sys

from . import __version__
from .core import GitError, find_drift, repo_root, untrack_commands


# Build the parser. Kept separate so tests can poke at the flags.
def build_parser():
    parser = argparse.ArgumentParser(
        prog="ignore-drift",
        description="Report tracked files that .gitignore rules say should not be tracked.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="any path inside the repository to inspect (default: current directory)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print a machine readable report instead of text",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="print the git rm --cached commands that would untrack the files",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="print nothing on a clean repository",
    )
    parser.add_argument(
        "--exit-zero",
        action="store_true",
        help="always exit 0, for reporting jobs that should not fail a build",
    )
    parser.add_argument("--version", action="version", version="ignore-drift " + __version__)
    return parser


# Turn the drift list into the text report a human reads.
def render_text(root, drift, show_fix):
    lines = []
    if not drift:
        lines.append("no drift in %s: every tracked file sits outside the ignore rules" % root)
        return "\n".join(lines)
    lines.append(
        "%d tracked file%s match an ignore rule in %s"
        % (len(drift), "" if len(drift) == 1 else "s", root)
    )
    lines.append("")
    for item in drift:
        lines.append("  %s" % item.path)
        lines.append("    matched %s from %s line %d" % (item.rule, item.source, item.line))
    lines.append("")
    lines.append(
        "git keeps versioning tracked files even when a rule matches them, so a secret or "
        "build artifact committed before the rule existed stays in the repository. "
        "Untrack each file with git rm --cached and commit the change."
    )
    if show_fix:
        lines.append("")
        lines.append("commands:")
        for command in untrack_commands(drift):
            lines.append("  " + command)
    return "\n".join(lines)


# Run the tool. Returns the process exit code so tests can assert on it.
def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        root = repo_root(os.path.abspath(args.path))
        drift = find_drift(root)
    except GitError as exc:
        sys.stderr.write("ignore-drift: %s\n" % exc)
        return 2

    if args.json:
        payload = {
            "repo": root,
            "count": len(drift),
            "drift": [
                {
                    "path": item.path,
                    "rule": item.rule,
                    "source": item.source,
                    "line": item.line,
                }
                for item in drift
            ],
        }
        print(json.dumps(payload, indent=2))
    elif drift or not args.quiet:
        print(render_text(root, drift, args.fix))

    if args.exit_zero:
        return 0
    return 1 if drift else 0
