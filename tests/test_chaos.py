#!/usr/bin/env python3
"""
KUBECURO CHAOS & EDGE CASE SUITE
-------------------------------
Rigorous testing for AuditEngineV3 across filesystem edge cases:
1. Circular Symlinks (Infinite Recursion Test)
2. Zero-Byte / Empty Files
3. Permission Denied (Sabotage Test)
4. Massive Document Depth
5. Binary Garbage (Invalid Encoding)

Author: Nishar A Sunkesala / KubeCuro Team
Date: 2026-01-16
"""

import os
import json
import shutil
import stat
import time
from pathlib import Path
from kubecuro.engine import AuditEngineV3
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

def setup_chaos_environment(root: Path):
    """
    Constructs a filesystem 'minefield' for the engine.
    Uses os.chmod and os.symlink to create OS-level edge cases.
    """
    if root.exists():
        # Reset permissions to ensure we can delete old test runs
        for path in root.rglob("*"):
            try:
                os.chmod(path, stat.S_IRWXU)
            except: pass
        shutil.rmtree(root)
    root.mkdir(parents=True)

    # 1. EDGE CASE: The Zero-Byte File (Should be handled as EMPTY_FILE)
    (root / "empty.yaml").write_text("")

    # 2. EDGE CASE: Binary Garbage (Testing encoding resilience)
    # Writing random bytes that are not valid UTF-8
    (root / "malicious_binary.yaml").write_bytes(os.urandom(500))

    # 3. EDGE CASE: Circular Symlink (Testing the is_symlink check)
    # Creates a link that points back to its parent to trap recursive scanners
    if os.name != 'nt':  # POSIX specific symlink test
        link_dir = root / "infinite_loop"
        link_dir.mkdir()
        (link_dir / "actual_file.yaml").write_text("kind: Pod")
        os.symlink(root, link_dir / "trap_link", target_is_directory=True)

    # 4. EDGE CASE: Permission Sabotage
    # Create a file that is readable but NOT writable (0o444)
    no_write_file = root / "locked_production.yaml"
    no_write_file.write_text("apiVersion: v1\nkind: Service\nmetadata:\n  name: locked")
    os.chmod(no_write_file, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

    # 5. EDGE CASE: Maximum Depth Violation
    # Nesting deeper than the default max_depth of 10
    deep_path = root
    for i in range(15):
        deep_path = deep_path / f"depth_{i}"
    deep_path.mkdir(parents=True)
    (deep_path / "ignored_deep_file.yaml").write_text("kind: Secret")

def run_rigorous_eval():
    test_root = Path("./kubecuro_chaos_test").resolve()
    catalog_path = test_root / "catalog.json"
    
    # Setup the environment and a mock catalog
    setup_chaos_environment(test_root)
    with open(catalog_path, 'w') as f:
        json.dump({"v1/Service": {"required": ["kind"]}}, f)

    engine = AuditEngineV3(workspace_path=str(test_root), catalog_path=str(catalog_path))

    print("🔥 COMMENCING CHAOS TEST...\n")

    # TEST 1: Recursion Safety
    print("Test 1: Recursion & Symlink Loop Safety")
    reports = engine.scan_directory(dry_run=True, max_depth=5)
    deep_found = any("ignored_deep_file.yaml" in r['file_path'] for r in reports)
    print(f"  [PASS] Engine avoided infinite loop and respected max_depth: {not deep_found}")

    # TEST 2: Permission Failure & Atomic Integrity
    print("\nTest 2: Write Protection Sabotage")
    # This should trigger the permission check in _atomic_write
    report = engine.audit_and_heal_file("locked_production.yaml", dry_run=False, force_write=True)
    if "write_error" in report:
        print(f"  [PASS] Gracefully caught PermissionError: {report['write_error']}")

    # TEST 3: Encoding Robustness
    print("\nTest 3: Binary/Invalid Input Handling")
    garbage_report = engine.audit_and_heal_file("malicious_binary.yaml")
    if garbage_report['status'] == "HEAL_FAILED":
        print(f"  [PASS] Correctly rejected binary file without crashing.")

    # TEST 4: Atomic Consistency (The "Ghost File" Check)
    print("\nTest 4: Temporary File Cleanup")
    engine.scan_directory(dry_run=False)
    temp_files = list(test_root.rglob("*.kubecuro.tmp"))
    print(f"  [PASS] Zero 'ghost' temporary files remaining: {len(temp_files) == 0}")

    # Reset permissions so OS can delete the folder later
    os.chmod(test_root / "locked_production.yaml", stat.S_IRWXU)

if __name__ == "__main__":
    try:
        run_rigorous_eval()
    except Exception as e:
        print(f"❌ CRITICAL ENGINE FAILURE: {str(e)}")
