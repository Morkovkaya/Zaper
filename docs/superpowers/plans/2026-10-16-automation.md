# Release and installation automation Implementation Plan

> **For agentic workers:** Execute inline in this session; verify each task before proceeding. No delegation is needed.

**Goal:** Successful main builds publish new Windows/Linux versions automatically; Linux installs dependencies and verified updates without manual extraction.

**Architecture:** Keep build/test jobs as the release gate. A trusted-main publisher consumes their exact artifacts and publishes only missing versions, Linux with latest=false for Windows updater compatibility. Linux root updater downloads authenticated GitHub metadata and digest-verified bytes into a private directory, rejects unsafe archive entries, and invokes the transactional installer. Dependency installation is explicit via install.sh --with-deps and uses distribution packages.

**Tech Stack:** GitHub Actions, gh CLI, Python standard library, POSIX shell, GTK3.

**Spec:** User request in this conversation: automate both release and installation/update processes; check everything.

## Global Constraints
- Preserve portable Arch support, X11 and native Wayland; no hardware/boot changes.
- Preserve settings, user lists, service enabled/running state on upgrade; initial install stays stopped.
- Publish only tested artifacts after both Windows and Linux jobs succeed; never replace a published release.
- Public repository needs no token; tokens are optional and never persisted.
- No execution of user-provided update paths as root. Reject path traversal, links and oversized archives.

### Task 1: Trusted automatic release gate
**Files:** scripts/release.py, scripts/tests/test_release.py, .github/workflows/build.yml, linux/zaper_version.py.
**Interfaces:** metadata() returns windows/linux versions and bundle; publish(directory) consumes downloaded CI artifacts.
- [x] Test version consistency, artifacts, immutable published versions, draft retry and failure paths with a mocked gh runner.
- [x] Generate dynamic Linux bundle paths in CI; bump Linux to 3.8.1-linux.4.
- [x] Publish missing versions on trusted main only after both test jobs. Draft first; upload checksums and assets; mark Windows latest and Linux latest=false. Keep workflow contents read except publisher.
- [x] Run tests, package locally, inspect diff; commit.

### Task 2: Dependency and transactional install
**Files:** linux/install.sh, linux/zaper_install.py, linux/tests/test_install.py, linux/tests/upgrade.sh.
**Interfaces:** install.sh install --with-deps installs distro packages then delegates existing install; transaction wrapper snapshots owned files and service state, invokes install.sh --files-only, restores on failure.
- [x] Test distro selection and package command arguments; refuse unsupported distributions without touching files; DESTDIR never installs dependencies.
- [x] Add Arch/Debian/Ubuntu/Fedora/openSUSE dependency selection; no full system upgrade.
- [x] Add private backup and rollback of owned installation files; preserve running state after successful upgrade and restart old service on failure.
- [x] Verify staged install and real disposable upgrade/rollback, including operation lock.

### Task 3: One-click Linux update
**Files:** linux/zaper_updates.py, linux/zaper_commands.py, linux/zapret_gui.py, linux/tests/test_updates.py.
**Interfaces:** install(token='') returns updated/version/restart_panel. CLI app-install is root only; GUI invokes installed privileged command and displays result.
- [x] Reject draft/prerelease and mismatched tag/asset versions; report current version without reinstall/downgrade.
- [x] Safely extract verified archive, require complete installer/runtime, invoke installer in private root directory; preserve token only in memory.
- [x] Add GUI install button and appropriate download/install timeout; tell user to reopen panel after update.
- [x] Test hostile archive entries, digest failure, no-op current version, root requirement, installer failure.

### Task 4: End-to-end delivery
**Files:** README.md, linux/README.md, docs/VALIDATION.md, workflow.
- [x] Document the dependency installer, one-click update and version-triggered automatic releases.
- [ ] Run all packaged tests and full CI (Windows, X11, Wayland, ARM64, real engine, old upgrades); fix any failures.
- [ ] Open and attach PR, merge after checks, observe main publishing Linux.4 automatically and verify public download SHA256.
