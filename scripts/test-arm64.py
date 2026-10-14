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
for game in ('off', 'tcp', 'udp', 'all'):
    for ipset in ('none', 'loaded', 'any'):
        for strategy in ('current', 'split', 'disorder'):
            result = subprocess.run(['qemu-aarch64', str(home / 'runtime/bin/arm64/nfqws2'), '--dry-run'] +
                manager.build_args(manager.Settings(game=game, ipset=ipset, strategy=strategy)),
                capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise SystemExit(result.stdout + result.stderr)
print('PASS: all 36 ARM64 profiles accepted by the real engine')
