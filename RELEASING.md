# Releasing Rein

Rein is released from this repository as a git tag plus a GitHub release.
It is not published on PyPI; users install it from the repository.

## Before the release

1. `main` is green in CI.
2. Decide which open pull requests make the cut.
3. Run the checks locally, the same way CI does:
   ```bash
   make lint && make test
   ```
4. Check what will actually ship, not the working directory:
   ```bash
   git archive HEAD | tar -t
   ```
   The exported tree must not contain credentials, private host names,
   personal data or references to private trackers.

## Bump the version

1. Update `rein/__init__.py` (the package version is read from it):
   ```python
   __version__ = "X.Y.Z"
   ```
2. Update `CHANGELOG.md`: move the Unreleased items under the new version
   heading with today's date.

## Commit, tag and push

```bash
git add rein/__init__.py CHANGELOG.md
git commit -m "Release vX.Y.Z"
git tag vX.Y.Z
git push origin main vX.Y.Z
```

The tag triggers `.github/workflows/release.yml`, which builds the sdist and
wheel and runs the tests on Python 3.10 and 3.12. The built files are kept as
artifacts of that workflow run.

## GitHub release

1. Create a GitHub release from the tag, with the highlights from `CHANGELOG.md`.
2. Attach any release assets (demo media, built files) to it.
3. Verify a clean install from the tag:
   ```bash
   pip install "rein-orchestrator @ git+https://github.com/dklymentiev/rein-orchestrator@vX.Y.Z"
   rein --version
   ```

## Hotfix process

For an urgent fix against a released version:

1. Branch from the release tag: `git checkout -b hotfix/X.Y.Z+1 vX.Y.Z`
2. Apply the fix and bump the patch version.
3. Merge to `main`, tag, and release as above.
