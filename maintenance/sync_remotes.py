# SPDX-License-Identifier: Apache-2.0
"""Preview or publish one reviewed code branch to GitHub and GitLab."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DESTINATIONS = {
    'origin': {'https://github.com/stefanjdecker/texstage.git',
               'git@github.com:stefanjdecker/texstage.git'},
    'gitlab': {'git@gitlab.git.nrw:rwth-dbis/infrastructure/texstage.git',
               'https://gitlab.git.nrw/rwth-dbis/infrastructure/texstage.git'},
}


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--branch', required=True, help='Local branch to publish under the same name')
    parser.add_argument('--push', action='store_true', help='Publish after both previews succeed')
    args = parser.parse_args()
    ref = 'refs/heads/' + args.branch
    git('check-ref-format', ref)
    sha = git('rev-parse', '--verify', ref + '^{commit}')
    subprocess.run([sys.executable, str(ROOT / 'maintenance/check_public_content.py'), '--rev', sha], check=True)
    if git('status', '--porcelain'):
        print('Working files contain uncommitted changes; only the named committed branch is included.', flush=True)
    for remote, allowed in DESTINATIONS.items():
        urls = git('remote', 'get-url', '--push', '--all', remote).splitlines()
        if len(urls) != 1 or urls[0] not in allowed:
            raise SystemExit(f'Refusing unexpected push destination for {remote}: configure the documented code remote.')
    print(f'Publishing {ref} at {sha}; force updates and branch deletions are not supported.', flush=True)
    for remote in DESTINATIONS:
        subprocess.run(['git', '-C', str(ROOT), 'push', '--dry-run', remote, f'{sha}:{ref}'], check=True)
    if not args.push:
        print('Both previews passed. Add --push to publish this branch to both hosts.')
        return
    for remote in DESTINATIONS:
        subprocess.run(['git', '-C', str(ROOT), 'push', remote, f'{sha}:{ref}'], check=True)
    for remote in DESTINATIONS:
        tips = git('ls-remote', '--heads', remote, ref).splitlines()
        if tips != [f'{sha}\t{ref}']:
            raise SystemExit(f'{remote} changed during publication; inspect both hosts before retrying.')
    print(f'Verified identical {ref} at both destinations: {sha}')


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc
