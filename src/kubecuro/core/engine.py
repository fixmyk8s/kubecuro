#!/usr/bin/env python3
"""
KUBECURO ENGINE - Version 3.0 (Production Hardened)
--------------------------------------------------
The AuditEngineV3 is the central orchestrator of the KubeCuro suite. 
It manages the lifecycle of a YAML manifest through five distinct phases:
1. Lexical Analysis (Sharding)
2. Structural Reconstruction (Schema-Aware Parsing)
3. Logical Shielding (Policy Enforcement)
4. Anti-Frankenstein Validation (Schema Verification)
5. Atomic Persistence (Safe Write)

This version is optimized for batch processing with recursion safety,
atomic file operations, and multi-document support.

Author: Nishar A Sunkesala / KubeCuro Team
Date: 2026-01-16
"""

import os
import shutil
import time
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

# Modular imports from the healing, rules, and validator sub-packages
from kubecuro.healing.pipeline import HealingPipeline
from kubecuro.healing.exporter import KubeExporter
from kubecuro.rules.shield import ShieldEngine
from kubecuro.validator.validator import KubeValidator

# Setup standardized logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kubecuro.engine")

class AuditEngineV3:
    """
    Principal Orchestrator for Kubernetes manifest healing.
    Maintains the state of the workspace and coordinates specialized engines.
    Includes safety gates for recursion depth and atomic write operations.
    """

    def __init__(self, workspace_path: str, catalog_path: str):
        """
        Initializes the V3 engine with a target workspace and a K8s schema catalog.
        
        Args:
            workspace_path: The root directory where YAML files are located.
            catalog_path: Path to the distilled K8s JSON schema for structural validation.
        """
        # Resolve the workspace to an absolute path for safety
        self.workspace = Path(workspace_path).resolve()
        
        # Load the Blueprint (Minified K8s OpenAPI Spec)
        # This catalog allows the Structurer to understand 'Expected' vs 'Found' fields.
        try:
            with open(catalog_path, 'r') as f:
                self.catalog = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            # Fatal error: Engine cannot function without its structural knowledge base
            logger.error(f"Critical Failure: Unable to load catalog from {catalog_path}")
            raise RuntimeError(f"Failed to load catalog: {str(e)}")
            
        # Initialize the specialized Healing Suite components
        # We pass the catalog to the pipeline so its internal Structurer is ready.
        self.pipeline = HealingPipeline(self.catalog)
        self.exporter = KubeExporter()
        self.shield = ShieldEngine()
        self.validator = KubeValidator(self.catalog)
        
        # Ensure the workspace is ready for operations
        self._ensure_workspace()

    def _ensure_workspace(self):
        """
        Validates that the target workspace exists. 
        Creates it if missing to prevent OS-level path errors during execution.
        """
        if not self.workspace.exists():
            logger.info(f"Workspace {self.workspace} not found. Creating directory...")
            self.workspace.mkdir(parents=True, exist_ok=True)

    def audit_and_heal_file(self, relative_path: str, dry_run: bool = True, 
                            force_write: bool = False, strict: bool = False) -> Dict[str, Any]:
        """
        Performs a full audit and healing cycle on a single file.
        
        Args:
            relative_path: The path to the file relative to the workspace root.
            dry_run: If True, content is processed but not written to disk.
            force_write: If True, allows writing even if the heal was only partial.
            strict: If True, fails validation on unknown fields (typos).
            
        Returns:
            A dictionary (report) containing the status, healed content, and logic logs.
        """
        # Build the absolute path for file system operations
        full_path = (self.workspace / relative_path).resolve()
        
        # --- PHASE 1: PRE-FLIGHT ---
        if not full_path.exists():
            return self._file_error(relative_path, "FILE_NOT_FOUND", f"File not found: {full_path}")

        # State tracking for the report
        success = False
        partial_heal = False
        is_modified = False
        final_yaml = ""
        display_status = "FAILED"
        context = None
        all_logic_logs = []
        validation_error = ""

        # --- PHASE 2: PROCESSING (The Surgery) ---
        try:
            # Read using utf-8-sig to handle Byte Order Marks (BOM) gracefully
            raw_text = full_path.read_text(encoding='utf-8-sig')

            # Pass 1: Lexical Pipeline (Lexer -> Shadow -> Scanner -> Structurer)
            context = self.pipeline.run(raw_text)
            healed_docs = context.reconstructed_docs or []
            
            # Pass 2: Logic Shielding & Anti-Frankenstein Validation
            protected_docs = []
            validation_passed = True

            for doc in healed_docs:
                # Shielding: Injecting resource limits, security contexts, etc.
                protected_doc, logs = self.shield.protect(doc)
                
                # Validation: Ensuring the heal didn't break K8s structural logic
                # FIXED: 'strict' is now correctly linked from the method signature
                valid, err = self.validator.validate_reconstruction(protected_doc, strict=strict)
                if not valid:
                    validation_passed = False
                    validation_error = err
                
                protected_docs.append(protected_doc)
                all_logic_logs.extend(logs)

            # Pass 3: Export to Canonical YAML
            # Joins documents back into a single string with '---' separators
            final_yaml = self.exporter.export(protected_docs, context)

            # Verification logic: Success requires valid documents and kind identification
            success = True if (context.kind and protected_docs and validation_passed) else False
            partial_heal = not success and len(context.shards) > 0
            
            # Check if the engine actually improved the file (normalized comparison)
            is_modified = raw_text.strip() != final_yaml.strip()

            # Determine the status for CLI reporting
            if not is_modified:
                display_status = "UNCHANGED"
            elif dry_run:
                display_status = "PREVIEW"
            else:
                display_status = "HEALED" if success else "PARTIAL" if partial_heal else "FAILED"

        except Exception as e:
            # Safeguard: prevent a single corrupt file from crashing the entire batch scan
            logger.error(f"Error processing {relative_path}: {str(e)}")
            return self._file_error(relative_path, "HEAL_FAILED", str(e))
        
        # --- PHASE 3: WRITE DECISION ---
        # A file is written only if it's modified, not a dry-run, and passes safety checks
        should_write = not dry_run and is_modified and (success or (partial_heal and force_write))
        
        # Run Git safety diagnostics
        git_recommendations = self.check_git_safety()

        # Prepare the comprehensive result dictionary
        result = {
            "file_path": str(relative_path),
            "success": success or not is_modified,
            "partial_heal": partial_heal,
            "status": display_status,
            "kind": context.kind if context else "Unknown",
            "api_version": context.api_version if context else "Unknown",
            "written": False,
            "backup_created": None,
            "healed_content": final_yaml if is_modified else None,
            "logic_logs": all_logic_logs,
            "validation_error": validation_error,
            "git_warnings": git_recommendations,
            "timestamp": time.time()
        }

        # --- PHASE 4: EXECUTION (Disk I/O) ---
        if should_write:
            # Create a backup before modifying any user data
            backup_path = self._create_unique_backup(full_path)
            try:
                # Use copy2 to preserve metadata (times, permissions)
                shutil.copy2(full_path, backup_path)
                result["backup_created"] = str(backup_path.relative_to(self.workspace))
            except Exception as e:
                result["backup_warning"] = f"Backup failed: {str(e)}"
            
            # Execute the update using an atomic write pattern
            try:
                self._atomic_write(full_path, final_yaml)
                result["written"] = True
            except IOError as e:
                result["write_error"] = str(e)
                result["success"] = False
        
        return result

    def _create_unique_backup(self, target_path: Path) -> Path:
        """
        Generates a unique filename for backups to avoid overwriting previous fixes.
        Format: filename.kubecuro.backup or filename-1.kubecuro.backup
        """
        backup_path = target_path.with_suffix('.kubecuro.backup')
        if backup_path.exists():
            counter = 1
            while True:
                new_name = f"{target_path.stem}-{counter}.kubecuro.backup"
                backup_path = target_path.with_name(new_name)
                if not backup_path.exists():
                    break
                counter += 1
        return backup_path

    def _atomic_write(self, target_path: Path, content: str):
        """
        Implements the Atomic Write Pattern. 
        Writes to a temporary file first, then renames it to the target.
        This prevents file corruption if the process is interrupted mid-write.
        """
        # Permission check before starting I/O
        if not os.access(target_path.parent, os.W_OK):
            raise PermissionError(f"No write permission in directory: {target_path.parent}")
            
        temp_file = target_path.with_suffix('.kubecuro.tmp')
        try:
            temp_file.write_text(content, encoding='utf-8')
            # OS-level move is atomic on most modern file systems (POSIX)
            os.replace(temp_file, target_path)
        except Exception as e:
            # Cleanup the temp file if the write fails to prevent 'Ghost Files'
            if temp_file.exists():
                temp_file.unlink()
            raise IOError(f"Atomic write failed: {str(e)}")

    def scan_directory(self, extension: str = ".yaml", dry_run: bool = True, 
                       force_write: bool = False, strict: bool = False, max_depth: int = 10,
                       progress_callback: Optional[Callable[[int, int], None]] = None) -> List[Dict[str, Any]]:
        """
        Recursively discovers and processes all YAML files within the workspace.
        """
        reports = []
        patterns = [f"*{extension.lower()}", f"*{extension.upper()}"]
        
        # Identify all candidate files (Exclude Symlinks for safety)
        all_files = []
        for p in patterns:
            all_files.extend([f for f in self.workspace.rglob(p) if f.is_file() and not f.is_symlink()])
        
        total_files = len(all_files)
        processed = 0

        for file_path in all_files:
            try:
                # Enforce directory depth limits to prevent infinite recursion
                depth = len(file_path.relative_to(self.workspace).parts)
                if depth > max_depth:
                    continue
                
                rel_path = str(file_path.relative_to(self.workspace))
                # FIXED: Correctly passing 'strict' argument to avoid TypeError
                report = self.audit_and_heal_file(rel_path, dry_run, force_write, strict=strict)
                reports.append(report)
                
            except Exception as e:
                logger.error(f"Unexpected error in scan loop for {file_path}: {str(e)}")
                continue
            
            processed += 1
            if progress_callback:
                progress_callback(processed, total_files)

        return reports

    def cleanup_backups(self, max_age_hours: int = 168) -> int:
        """
        Maintenance utility to remove old .kubecuro.backup files.
        Default is 168 hours (7 days).
        """
        count = 0
        cutoff = time.time() - (max_age_hours * 3600)
        
        for backup in self.workspace.rglob("*.kubecuro.backup"):
            try:
                if backup.stat().st_mtime < cutoff:
                    backup.unlink()
                    count += 1
            except OSError:
                continue
        return count
        
    def check_git_safety(self) -> List[str]:
        """
        Diagnostic utility to ensure KubeCuro artifacts don't pollute 
        the version control system. 
        """
        warnings = []
        gitignore = self.workspace / ".gitignore"
        
        if (self.workspace / ".git").exists() and gitignore.exists():
            try:
                content = gitignore.read_text(encoding='utf-8')
                
                if "*.kubecuro.backup" not in content:
                    warnings.append(
                        "Recommendation: Add '*.kubecuro.backup' to .gitignore. "
                        "WHY: Prevents snapshot files from being accidentally committed."
                    )
                
                if "*.kubecuro.tmp" not in content:
                    warnings.append(
                        "Recommendation: Add '*.kubecuro.tmp' to .gitignore. "
                        "WHY: Prevents 'half-written' temporary files from entering the repo."
                    )
            except Exception:
                pass
        
        return warnings

    def generate_summary(self, reports: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyzes a list of reports to provide an SRE-style performance summary.
        """
        if not reports:
            return {"total_files": 0, "success_rate": 0}

        total = len(reports)
        successful = sum(1 for r in reports if r.get('success', False))
        partial = sum(1 for r in reports if r.get('partial_heal', False))
        backups = sum(1 for r in reports if r.get('backup_created'))
        writes = sum(1 for r in reports if r.get('written', False))
        
        return {
            "total_files": total,
            "success_rate": (successful / total) if total > 0 else 0,
            "successful": successful,
            "partial_heal": partial,
            "backups_created": backups,
            "written_to_disk": writes,
            "summary_timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }

    def _file_error(self, relative_path: str, status: str, error: str) -> Dict[str, Any]:
        """Standardized error structure for file-level failures."""
        return {
            "file_path": relative_path, "status": status, "error": error,
            "success": False, "partial_heal": False, "kind": "Unknown"
        }
