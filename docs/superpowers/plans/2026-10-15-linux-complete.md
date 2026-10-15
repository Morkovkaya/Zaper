# Complete Linux parity implementation plan

> Execute inline in the existing feature branch with verification before publication.

**Goal:** Finish the Linux equivalents of Windows 3.8.1 and complete GitHub delivery, including merging the verified PR.
**Architecture:** Add bounded cancellable network probes and a transactional auto-tuner using the existing operation lock and durable recovery journal. Add an unprivileged loopback upload relay with per-user desktop proxy snapshots, ownership-aware recovery and an independent watchdog. Expose these in CLI and GUI, preserve existing configuration and portable hardware support.
**Tech Stack:** Python 3.10+, asyncio, curl, Tk, nftables, optional systemd and GNOME/KDE desktop settings.
**Spec:** src/Network.cs, Relay.cs, Core.cs and App.cs at origin/main; user request “переноси полностью + доконца доделай работу с гитхабом”.

## Global constraints

- Never alter the development host's proxy, network, Hosts, drivers or boot settings. Use fixtures and disposable runners for all mutations.
- Preserve existing user settings and old service/CLI identifiers; do not overwrite a newer desktop proxy chosen by the user during recovery.
- Keep cancellation responsive and restore both configuration and prior service running state. Record pending state before changing anything; recover interrupted tuning before the next engine start.
- Linux process exclusions use UID/IP/domain rules; Windows EXE identity and Windows service/registry actions have Linux equivalents.

### Task 1: Settings and network diagnostics
Files: linux/zapret_manager.py, zaper_state.py, new zaper_network.py, tests/test_network.py.
- [ ] Add validated Discord/game fake selection, auto-check, separate FACEIT server exclusions; preserve Windows profile fields on import.
- [ ] Implement cancellable curl probes with semantic content validation, optional HTTP/3 capability detection, STUN transaction validation, FACEIT region/HTTPS/A2S challenge diagnostics.
- [ ] Test malformed STUN/A2S, semantic HTTPS failures, cancellation cleanup and all fake/strategy configurations with the real engine.

### Task 2: Auto-tune and recovery
Files: new linux/zaper_tune.py, zaper_commands.py, zapret_gui.py, tests/test_tune.py.
- [ ] Implement Windows winner policy (success ratio, P90/median and 15%/50ms hysteresis), all nine candidates and finalist recheck.
- [ ] Persist original bytes/running state and history under operation lock; rollback on failure/cancel; recover after SIGKILL before next start. Preserve last successful backup for explicit undo.
- [ ] Expose run/cancel/recover/results; GUI shows progress without blocking Tk. Test success, all-fail, cancel, journal recovery, locked concurrency and prior running/stopped state.

### Task 3: Upload proxy limiter
Files: new linux/zaper_proxy.py, zapret_gui.py, zaper_commands.py, tests/test_proxy.py.
- [ ] Add aggregate upload pacing (1–1000 Mbps), unrestricted downloads, half-close forwarding, bounded connection cleanup and loopback-only endpoints.
- [ ] Add explicit GNOME/KDE desktop integration and manual endpoint mode; snapshots, rollback, crash watchdog, next-login recovery, ownership-aware restoration and duplicate-instance lock.
- [ ] Test real concurrent transfers/rate bounds/half-close, desktop adapter fixtures, relay crash recovery, startup failure, port collision and preserving an externally changed proxy.

### Task 4: Delivery
Files: linux/README.md, version/workflow/tests/installer, docs/VALIDATION.md.
- [ ] Update GUI smoke and CI for new functions and regression cases; package 3.8.1-linux.2 and test legacy migrations.
- [ ] Run full Linux/Windows CI, download only successful build artifacts and verify archive checksum after publishing.
- [ ] Update PR description, merge after required checks, verify main build and publish final Linux release from the same verified source. Document runtime capability limits without claiming provider-specific connectivity.
