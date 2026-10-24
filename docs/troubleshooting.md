# Troubleshooting

**A check says `blocked`.** The effective permissions do not cover what the check needs.
`archonix check plan . --mode audit` shows the reason; add `--allow-tools`,
`--allow-repo-code` or `--allow-network` only if that is authorized. `archonix config show .`
shows where each permission came from; your `archonix.toml` cannot enable permissions.

**A check says `skipped: … is not installed`.** The tool is not on the PATH Archonix sees.
Install it, or activate the environment that has it. Archonix never installs tools.

**`parse-error`.** The tool's output was malformed, truncated (raise
`execution.max_output_bytes`) or in an unexpected format/version. Findings for that check
are unknown; the report says so.

**`tool-error` with an exit code.** The tool failed (bad config, crash, pytest exit 5 = no
tests collected). The report records stderr (redacted, bounded).

**`timeout`.** Raise `execution.timeout_seconds` or `checks.<id>.timeout_seconds`, or
`ARCHONIX_TIMEOUT_SECONDS`. The whole process group was terminated.

**Revision is `none` / dirty is `unknown`.** The directory is not a Git repository, or
`git status` was not permitted (add `--allow-tools`) or failed.

**`refusing to write through … it is a symlink inside the scanned repository`.** The
output path goes through a symlink that the repository itself contains, so the
repository could redirect writes elsewhere. Use a directory outside the repository,
for example `out="$(mktemp -d)"`.

**`refusing to write … outside the allowed locations` / `not empty`.** Choose a new
`--out-dir`, or pass `--overwrite` deliberately.

**Installer reports a conflict.** A skill directory exists that Archonix did not create, or
you edited installed files. Nothing was changed. Move your copy aside or remove the
modified files yourself, then re-run.

**The assistant does not pick up the skill.** Check the path in
[assistants.md](assistants.md), run `archonix skill validate <path>`, ensure `SKILL.md`
starts with `---` on line 1, and restart or reload skills in the assistant.

**Ruff reports nothing on a nested project.** Ruff uses the closest `pyproject.toml`
with a `[tool.ruff]` section; a parent config's `exclude` can apply. Add a `[tool.ruff]`
section to the nested project.

**YAML OpenAPI files.** `pip install pyyaml`, or convert the document to JSON.

**Installer reports a symlink conflict.** The target directory, a file or directory inside
it, or (for `--scope project`) a directory between the project root and the target is a
symlink. Archonix refuses to write or delete through symlinks. Replace the link with a real
directory, or install with `--scope user` if you manage `~/.claude` through dotfiles
(a symlinked `~/.claude` itself is supported).

**A tool is "not installed" although it runs in your shell.** Archonix ignores empty and
relative `PATH` entries (such as `.` or `node_modules/.bin`) so a repository cannot
substitute its own executables. Put the tool's directory on `PATH` as an absolute path.

**Report says an artifact "could not be redacted, and was removed".** A retained artifact
that is binary, larger than 20 MB, unreadable or a symlink cannot be redacted, so it is
removed from the output directory and named in the report's limitations. This happens
on every exit path, including timeouts. Re-run with a larger limit or inspect the tool
directly if you need that file.
