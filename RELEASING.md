# Releasing

Publishing a GitHub release triggers `.github/workflows/release.yml`, which validates,
builds, and uploads to PyPI through trusted publishing. A draft release does not trigger
publication. Recheck the workflow and `pypi` environment protections before each
release; do not assume there is a later manual approval gate. PyPI releases are
immutable.

1. **Prepare.** Check live GitHub releases, PyPI versions, remote tags, and worktree
   state. Review changes since the previous release and propose a version and full
   commit SHA from current `origin/main`. Preserve existing work. Versions come from
   `vVERSION` tags through hatch-vcs; no version-bump commit is needed.
2. **Validate.** At that clean commit, run `nix fmt -- --ci`, `nix flake check`, and
   `nix build`. Inspect candidate wheel/sdist metadata, dependency constraints, typing
   marker, and license; rebuild the sdist and run the README example against an isolated
   installed wheel. Read current compatibility pins from `pyproject.toml`. A
   pretend-version candidate is preparation evidence, not an artifact to publish.
3. **Draft.** Obtain explicit approval before creating/pushing the tag or creating the
   GitHub draft release. Bind the tag to the approved SHA; preserve existing tags.
   Create the release with `gh release create vVERSION --verify-tag --draft`, using
   title `pytest-otel-capture VERSION` and the notes format below.
4. **Review.** Inspect the draft's rendered layout and wording with the user. Describe
   this project's changes precisely: distinguish allowed dependency ranges from tested
   upstream versions, and attribute upstream fixes to upstream. Claim security fixes
   only with evidence. Rebuild from the approved tag with pretend-version overrides
   unset, inspect the artifacts, and run `scripts/check-release.py` with `RELEASE_TAG`
   and `DIST_DIR` set. Stop on any validation failure.
5. **Publish.** Obtain explicit approval of the current draft and its automatic PyPI
   upload, then publish the draft. The workflow builds the tagged source again; the
   publish job uploads those validated artifacts rather than rebuilding them. If API
   access is denied, hand off the draft URL or exact command and notes to the user.
6. **Verify.** Confirm the release workflow succeeds, PyPI has the expected version and
   dependency metadata, and a fresh installation from PyPI runs the README example.
   Report the GitHub release and PyPI links, or the exact blocker.

## Release notes

Use short bullets under these headings, omitting empty sections. Include only changes
since the previous release; keep preparation logs and validation transcripts local.

- **Highlights:** user-visible additions and fixes.
- **Compatibility:** dependency-range changes and exact upstream versions tested.
- **Deprecations:** affected APIs and their replacements.
- **Full changelog:** link to
  `https://github.com/adamcik/pytest-otel-capture/compare/vPREVIOUS...vVERSION`.
