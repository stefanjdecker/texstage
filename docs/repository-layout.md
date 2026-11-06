# Code, plugins and private media

Develop Texstage in one code checkout. The same reviewed code commits go to
[GitHub](https://github.com/stefanjdecker/texstage) and the
[GitLab code mirror](https://gitlab.git.nrw/rwth-dbis/infrastructure/texstage).
GitHub is the source for new clones and incoming code changes.

| Project | Contents | Working folder |
| --- | --- | --- |
| Texstage | Application, styles, public examples, tests and manuals | `texstage` for fresh clones; `texstage-public` in the existing local setup |
| Texstage plugins | Plugin collection and independent plugin packages | `texstage-plugins` |
| Texstage media (private) | Demonstration video, script, transcript, captions and narrated showcase source | `texstage-media` |
| Lecture tools | Course assembly, notebooks and DBIS styles | `lecture-tools-next` |

Media production is independent of the software package. The public showcase
remains runnable in the code repository. Its synthetic in-slide clip is public;
the narrated demonstration and production script belong in the private media
repository. Do not add the media repository as a submodule or merge its history
into this repository.

## Set up one code checkout

```sh
git clone https://github.com/stefanjdecker/texstage.git texstage
cd texstage
git config core.hooksPath .githooks
git remote add gitlab git@gitlab.git.nrw:rwth-dbis/infrastructure/texstage.git
git config --unset-all remote.gitlab.fetch
git config --add remote.gitlab.fetch +refs/heads/main:refs/remotes/gitlab/main
git config --add remote.gitlab.fetch +refs/heads/codex/plugin-system:refs/remotes/gitlab/codex/plugin-system
git config remote.gitlab.tagOpt --no-tags
```

`origin` fetches and pushes GitHub; `gitlab` pushes the same code to GitLab.
Fetch GitLab only after its corresponding branch has been converted to the
clean code history. The restricted fetch list prevents accidentally importing
legacy private branches during the transition. Never fetch the media or legacy
private repository into the code checkout.

## Publish reviewed code to both hosts

Commit the intended changes on a feature branch and run the relevant checks.
Preview publication of one branch:

```sh
python maintenance/sync_remotes.py --branch codex/plugin-system
```

After reviewing the preview, publish it:

```sh
python maintenance/sync_remotes.py --branch codex/plugin-system --push
```

Use `--branch main` for a reviewed main-branch update. The helper checks the
public-content boundary, verifies both destination URLs, and dry-runs both
pushes before changing either host. It pushes one pinned commit with ordinary
fast-forward rules, then verifies both remote tips. Uncommitted files are not
published. Cross-host pushes are not atomic: if the second push fails, fix that
failure and rerun the same command. Do not use `git push --mirror`, `--all` or
force pushes for routine synchronization.

The pre-push guard checks each proposed commit and its complete ancestry, even
when the destination is private GitLab. This keeps both code destinations safe
to publish. See [releasing.md](releasing.md) for the remaining release checks.

## Existing courses and the former two checkouts

Keep existing course toolchain pins unchanged. A checked-out branch does not
retarget a pinned course installation. Build and test a new version before
explicitly updating an individual course's toolchain file.

The existing local setup uses `texstage-public` as its one active code checkout,
with both `origin` (GitHub) and `gitlab` remotes. Older
`--texstage-source ../texstage-public` commands continue to work. There is no
second active copy of the application to update or cherry-pick into.

The old private `texstage` folder is archived in place because Windows refused
its directory rename. It retains the previous private history and working files
for recovery, and its push hook blocks publication. Do not develop there or use
its former media workflow. Use `texstage-media` for all new recording work.

Both original histories and working-file snapshots were saved before the move.
The active code history is the previously cleaned public history. Converting
GitLab's old branches requires a separate one-time migration with exact old-tip
checks; the ordinary synchronization helper deliberately refuses that rewrite.
