# SPDX-License-Identifier: Apache-2.0
"""Reject private recording assets and narration in public Git history."""
from pathlib import Path
import argparse
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_PATHS = (
    'docs/media/demo/', 'docs/demonstration.md',
    'docs/demonstration-transcript.md',
    'examples/showcase/VIDEO-SCRIPT.md', 'examples/showcase/RECORDING.md',
)
SHOWCASE = 'examples/showcase/showcase.tex'


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def private(path):
    return any(path.startswith(p) if p.endswith('/') else path == p for p in PRIVATE_PATHS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rev', help='Check this proposed push tip and its complete ancestry')
    args = parser.parse_args()
    revisions = [args.rev] if args.rev else ['--all']
    errors = []
    for path in git('ls-files', '-z').decode().split('\0'):
        if private(path):
            errors.append('tracked private asset: ' + path)
    history_paths = git('log', *revisions, '--format=', '--name-only', '--', *PRIVATE_PATHS).decode()
    if history_paths.strip():
        errors.append('private paths occur in commit history: ' + history_paths.strip())
    objects = git('rev-list', '--objects', *revisions).decode().splitlines()
    notes = set()
    for item in objects:
        oid, _, path = item.partition(' ')
        if private(path):
            errors.append('history contains private asset: ' + path)
        if path == SHOWCASE:
            notes.add(oid)
    for oid in notes:
        content = git('cat-file', 'blob', oid)
        if re.search(rb'\b(?:SAY|SHOW):|VIDEO-SCRIPT\.md|RECORDING\.md', content):
            errors.append('history contains recording narration in showcase: ' + oid)
    staged = git('ls-files', '--stage', '--', SHOWCASE).decode()
    if staged:
        oid = staged.split()[1]
        if re.search(rb'\b(?:SAY|SHOW):|VIDEO-SCRIPT\.md|RECORDING\.md', git('cat-file', 'blob', oid)):
            errors.append('staged showcase contains recording narration')
    if errors:
        raise SystemExit('\n'.join(sorted(set(errors))))
    print('PASS: no private recording assets or narration in tracked files and reachable history')


if __name__ == '__main__':
    main()
