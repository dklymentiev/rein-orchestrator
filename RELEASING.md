# Releasing Rein

Step-by-step process for publishing a new version.

## Pre-release Checklist

1. Ensure `main` is green -- all CI checks passing
2. Review open PRs and decide what makes the cut
3. Run the full test suite locally:
   ```bash
   make lint && make test && make typecheck
   ```
4. Run release hygiene check (English-only, no emoji, no non-ASCII):
   ```bash
   make check-release
   ```

## Bump Version

1. Update `rein/__init__.py`:
   ```python
   __version__ = "X.Y.Z"
   ```
2. Update `VERSION` file:
   ```
   X.Y.Z
   ```
3. Update `CHANGELOG.md` -- move Unreleased items under the new version heading with today's date

## Create Release Commit

```bash
git add rein/__init__.py VERSION CHANGELOG.md
git commit -m "Release vX.Y.Z"
git push origin main
```

## Tag and Push

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

This triggers the `release.yml` workflow which builds and publishes to PyPI via trusted publishing.

## Post-release

1. Verify the package appears on [PyPI](https://pypi.org/project/rein-ai/)
2. Create a GitHub Release from the tag with highlights from CHANGELOG
3. Test install from PyPI:
   ```bash
   pip install rein-ai==X.Y.Z
   rein --version
   ```

## Hotfix Process

For urgent fixes against a released version:

1. Branch from the release tag: `git checkout -b hotfix/X.Y.Z+1 vX.Y.Z`
2. Apply the fix and bump patch version
3. Merge to `main`, tag, and release as above

## Yanking a Release

If a release has a critical defect:

```bash
pip install twine
twine yank rein-ai X.Y.Z --reason "brief reason"
```

Then publish a fixed version immediately.
