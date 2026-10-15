# Windows release and portable Linux implementation plan

> **For agentic workers:** Execute this plan task-by-task in the current isolated clone, with verification at each checkpoint.

**Goal:** Publish the existing Windows 3.6.3 installer and deliver a native, portable Linux manager for review.

**Architecture:** Keep Windows sources intact. Use Python 3 standard-library CLI and Tk GUI on Linux with the official static nfqws2 runtime, nftables in a dedicated table, and an optional systemd service. Keep privileged operations in the installed root-owned CLI.

**Tech Stack:** .NET Framework 4.8, Inno Setup, GitHub Actions, Python >=3.10, Tk, nftables, nfqws2 1.0.5.2.

**Spec:** User request: release Windows, add a universal Linux port, verify throughout; preserve portability across PCs.

## Global Constraints

- No hardcoded network interfaces, device paths, machine drivers, boot changes, or host firewall changes during development.
- Linux builds for x86_64 and aarch64; CLI supports Linux without systemd through foreground mode.
- Never flush the existing firewall. Remove only the manager's owned table.
- Retain upstream licenses and verify pinned runtime checksums.
- Publish Windows from the existing main commit; submit Linux and CI changes through a PR.

### Task 1: Reproducible Windows artifact

Files: `.github/workflows/build.yml`, `scripts/test-windows.ps1`.
- [x] Build with `powershell -File build.ps1 -InnoCompiler ...` on Windows.
- [x] Configure isolated payload and run `--self-test`, `--ui-test`, and `--test-package-service`; require exit 0 and PASS reports.
- [x] Install/uninstall with `/TESTMODE=1 /DIR=<temporary directory>` and check installed payload.
- [x] Upload installer and test evidence only after successful checks.

### Task 2: Linux backend and UI

Files: `linux/zapret_manager.py`, `linux/zapret_gui.py`, `linux/install.sh`, `linux/zapret2-manager.service`, `linux/README.md`, `linux/tests/test_manager.py`.
- [x] Build profiles from the existing runtime template, dropping WinDivert-only arguments and translating file paths into argv tokens.
- [x] Validate all configurations using `nfqws2 --dry-run`; test invalid inputs, profile coverage, queue loops and rollback.
- [x] Supervise nfqws2 and install an owned nftables table after queue readiness. Use bypass, IPv4/IPv6, fwmark loop protection and atomic cleanup on signals/errors.
- [x] Add settings, domain/IP exclusions, game modes, diagnostics, optional systemd management, and nonprivileged Tk GUI.
- [x] Install to root-owned `/opt/zapret2-manager`; preserve settings; test staging install/uninstall without touching host services.

### Task 3: Packaging and verification

Files: `scripts/package-linux.py`, workflow Linux job, root README.
- [x] Package pinned static x86_64/aarch64 runtimes with licenses, sources links and SHA256 manifest.
- [x] Run unit tests, all engine profile dry runs, GUI smoke test in Xvfb, and isolated network namespace lifecycle tests.
- [x] Repeat checks on Debian and Fedora; run aarch64 dry runs with QEMU.
- [x] Publish verified Windows release; attach the Linux preview to a prerelease and open PR #1 with accurate validation limits.
