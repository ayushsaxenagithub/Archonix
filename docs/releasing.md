# Releasing

Archonix publishes to PyPI from GitHub Actions with
[trusted publishing](https://docs.pypi.org/trusted-publishers/): PyPI trusts this
repository's `release.yml` workflow through OIDC, so no API token is stored anywhere.

## One-time setup (manual, by the repository owner)

Nothing below can be done from code in this repository.

1. **PyPI trusted publisher.** On <https://pypi.org/manage/account/publishing/>, add a
   *pending* publisher: project `archonix`, owner `ayushsaxenagithub`, repository
   `Archonix`, workflow `release.yml`, environment `pypi`. The project is created on the
   first successful upload.
2. **TestPyPI (optional, recommended for the first release).** Same on
   <https://test.pypi.org/manage/account/publishing/> with environment `testpypi`.
3. **GitHub environments.** Settings → Environments: create `pypi` (and `testpypi`), and
   add yourself as a required reviewer so every publish waits for an explicit approval.
4. **Branch protection** on `main` (see [maintainers.md](maintainers.md)), so releases are
   cut only from reviewed commits.

## Checklist for each release

1. On a branch: bump `version` in `pyproject.toml` and `src/archonix/__init__.py`
   (a test checks they match), and move the `[Unreleased]` notes in `CHANGELOG.md` under
   the new version with today's date.
2. Update `docs/capabilities.md` and `docs/roadmap.md` if capabilities changed;
   regenerate `examples/reports/` with `scripts/regenerate_examples.sh` if output formats
   changed.
3. Open a pull request; merge only when every required check is green.
4. Optional dry run: Actions → **Release** → *Run workflow* publishes the build to
   TestPyPI. Then `pipx install --index-url https://test.pypi.org/simple/ --pip-args
   "--extra-index-url https://pypi.org/simple/" archonix` and run `archonix --version`.
5. Create and publish a GitHub release with tag `vX.Y.Z` on the merge commit. The
   workflow verifies that the tag matches the version and that `CHANGELOG.md` has an
   entry, builds, runs `twine check --strict`, smoke-tests the wheel in an isolated
   environment, then waits for approval on the `pypi` environment before uploading.
6. Verify: `pipx install archonix==X.Y.Z && archonix --version && archonix skill validate`.

A version number can never be reused on PyPI, even after deleting a release. Yanking is
possible for broken releases; deleting is not a fix.
