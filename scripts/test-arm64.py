#!/usr/bin/env python3
"""Validate every profile with the actual ARM64 binary under QEMU."""
import importlib.util
from pathlib import Path
import subprocess
import sys

home = Path(sys.argv[1]).resolve()
spec = importlib.util.spec_from_file_location('zapret_manager', home / 'zapret_manager.py')
manager = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = manager
spec.loader.exec_module(manager)
count = 0
for game in ('off', 'tcp', 'udp', 'all'):
    for ipset in ('none', 'loaded', 'any'):
        for strategy in manager.STRATEGIES:
            for preset in ('native', 'alt12-exp'):
                result = subprocess.run(['qemu-aarch64', str(home / 'runtime/bin/arm64/nfqws2'), '--dry-run'] +
                    manager.build_args(manager.Settings(game=game, ipset=ipset, strategy=strategy, game_udp_preset=preset)),
                    capture_output=True, text=True, timeout=30)
                if result.returncode:
                    raise SystemExit(result.stdout + result.stderr)
                count += 1
print(f'PASS: all {count} ARM64 profiles accepted by the real engine')
