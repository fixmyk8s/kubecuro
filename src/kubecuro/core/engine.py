#!/usr/bin/env python3
"""
KUBECURO ENGINE - The High Orchestrator
---------------------------------------
The AuditEngineV3 manages the lifecycle of a YAML manifest through 
the 5 phases of KubeCuro healing. It ensures atomic persistence, 
batch recursion safety, and workspace integrity.

Author: Nishar A Sunkesala / KubeCuro Team
Date: 2026-01-16
"""

import os
import sys
import shutil
import time
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

# Modular imports aligned with the 2026-01-16 surgical suite
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
    Maintains workspace state and coordinates specialized engines 
    with safety gates for recursion depth and atomic write operations.
    """

    def __init__(self, workspace_path: str, catalog_path: str, 
                 cpu: str = "500m", mem: str = "512Mi"):
        """
        Initializes the V3 engine with workspace and K8s schema catalog.
        """
        self.workspace = Path(workspace_path).resolve()
        
        # Support for PyInstaller binary environments via _MEIPASS
        base_path = getattr(sys, '_MEIPASS', os.path.abspath("."))
        resolved_catalog = Path(base_path) / catalog_path

        try:
            # Fallback for local development structures if PyInstaller path fails
            if not resolved_catalog.exists():
                resolved_catalog = Path(catalog_path).resolve()

            with open(resolved_catalog, 'r') as f:
                self.catalog = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Critical Failure: Unable to load catalog from {resolved_catalog}")
            raise RuntimeError(f"Failed to load catalog: {str(e)}")
            
        # Initialize the specialized Healing Suite components
        self.pipeline = HealingPipeline(self.catalog)
        self.exporter = KubeExporter()
        self.validator = KubeValidator(self.catalog)
        
        # Shield is initialized with CLI-provided limits
        self.shield = ShieldEngine(cpu_limit=cpu, mem_limit=mem)
        
        self._ensure_workspace()

    def _ensure_workspace(self):
        """Validates/Creates target workspace to prevent OS path errors."""
        if not self.workspace.exists():
            logger.info(f"Creating missing workspace: {self.workspace}")
            self.workspace.mkdir(parents=True, exist_ok=True)

    def audit_and_heal_file(self, relative_path: str, dry_run: bool = True, 
                            force_write: bool = False, strict: bool = False,
                            target_version: str = "v1.31") -> Dict[str, Any]:
        """
        Performs a full audit and healing cycle on a single manifest.
        """
        full_path = (self.workspace / relative_path).resolve()
        
        if not full_path.exists():
            return self._file_error(relative_path, "FILE_NOT_FOUND", f"Path missing: {full_path}")

        # State Tracking
        success = False
        partial_heal = False
        is_modified = False
        final_yaml = ""
        all_logic_logs = []
        validation_error = ""

        try:
            # Phase 1: Read (BOM-aware)
            raw_text = full_path.read_text(encoding='utf-8-sig')

            # Phase 2: Healing Pipeline (Surgery)
            context = self.pipeline.run(raw_text)
            context.cluster_version = target_version
            healed_docs = context.reconstructed_docs or []
            
            # Phase 3: Shielding & Validation
            protected_docs = []
            validation_passed = True

            for doc in healed_docs:
                protected_doc, logs = self.shield.protect(doc)
                
                # Verify that the heal didn't break K8s structural logic
                valid, err = self.validator.validate_reconstruction(protected_doc, strict=strict)
                if not valid:
                    validation_passed = False
                    validation_error = err
                
                protected_docs.append(protected_doc)
                all_logic_logs.extend(logs)

            # Phase 4: Canonical Export
            final_yaml = self.exporter.export(protected_docs, context)

            # Verification logic
            success = bool(context.kind and protected_docs and validation_passed)
            partial_heal = not success and len(context.shards) > 0
            is_modified = raw_text.strip() != final_yaml.strip()

            # CLI Status mapping
            display_status = self._derive_status(is_modified, dry_run, success, partial_heal)

        except Exception as e:
            logger.error(f"Error processing {relative_path}: {str(e)}")
            return self._file_error(relative_path, "ENGINE_ERROR", str(e))
        
        # Phase 5: Result Construction
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
            "git_warnings": self.check_git_safety(),
            "timestamp": time.time()
        }

        # Execution (Disk I/O)
        if not dry_run and is_modified and (success or (partial_heal and force_write)):
            backup_path = self._create_unique_backup(full_path)
            try:
                shutil.copy2(full_path, backup_path)
                result["backup_created"] = str(backup_path.relative_to(self.workspace))
            except Exception as e:
                result["backup_warning"] = f"Backup failed: {str(e)}"
            
            try:
                self._atomic_write(full_path, final_yaml)
                result["written"] = True
            except IOError as e:
                result["write_error"] = str(e)
                result["success"] = False
        
        return result

    def scan_directory(self, extension: str = ".yaml", dry_run: bool = True, 
                       force_write: bool = False, strict: bool = False, 
                       target_version: str = "v1.31", max_depth: int = 10,
                       progress_callback: Optional[Callable[[int, int], None]] = None) -> List[Dict[str, Any]]:
        """
        Recursively discovers and processes all YAML files with safety gates.
        """
        try:
            max_depth = int(max_depth)
        except (ValueError, TypeError):
            logger.warning(f"Invalid max_depth '{max_depth}'. Falling back to default: 10")
            max_depth = 10
            
        reports = []
        patterns = [f"*{extension.lower()}", f"*{extension.upper()}"]
        
        # Phase 1: File Discovery (Exclude symlinks to prevent loops)
        all_files = []
        for p in patterns:
            all_files.extend([f for f in self.workspace.rglob(p) if f.is_file() and not f.is_symlink()])
        
        total_files = len(all_files)
        processed = 0

        # Phase 2: Processing Loop
        for file_path in all_files:
            try:
                # Recursion depth check
                rel_parts = file_path.relative_to(self.workspace).parts
                if len(rel_parts) > max_depth:
                    continue
                
                rel_path = str(file_path.relative_to(self.workspace))
                report = self.audit_and_heal_file(
                    rel_path, 
                    dry_run=dry_run, 
                    force_write=force_write, 
                    strict=strict, 
                    target_version=target_version
                )
                reports.append(report)
                
            except Exception as e:
                logger.error(f"Critical error in scan loop for {file_path}: {str(e)}")
                continue
            
            processed += 1
            if progress_callback:
                progress_callback(processed, total_files)

        return reports

    def cleanup_backups(self, max_age_hours: int = 168) -> int:
        """Removes old backup files (default 7 days)."""
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

    def generate_summary(self, reports: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Provides SRE-style performance metrics."""
        if not reports:
            return {
                "total_files": 0, "success_rate": 0, "successful": 0, 
                "system_errors": 0, "backups_created": 0
            }

        total = len(reports)
        successful = sum(1 for r in reports if r.get('success', False))
        writes = sum(1 for r in reports if r.get('written', False))
        backups_count = sum(1 for r in reports if r.get('backup_created') is not None)
        system_errors = sum(1 for r in reports if r.get('status') == "ENGINE_ERROR")
        
        return {
            "total_files": total,
            "success_rate": (successful / total) if total > 0 else 0,
            "successful": successful,
            "written_to_disk": writes,
            "backups_created": backups_count,
            "system_errors": system_errors,
            "summary_timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }

    def _derive_status(self, modified, dry, success, partial) -> str:
        if not modified: return "UNCHANGED"
        if dry: return "PREVIEW"
        if success: return "HEALED"
        return "PARTIAL" if partial else "FAILED"

    def _atomic_write(self, target_path: Path, content: str):
        if not os.access(target_path.parent, os.W_OK):
            raise PermissionError(f"No write access to {target_path.parent}")
        temp_file = target_path.with_suffix('.kubecuro.tmp')
        try:
            temp_file.write_text(content, encoding='utf-8')
            os.replace(temp_file, target_path)
        except Exception as e:
            if temp_file.exists(): temp_file.unlink()
            raise IOError(f"Atomic write failed: {str(e)}")

    def _create_unique_backup(self, target_path: Path) -> Path:
        backup_path = target_path.with_suffix('.kubecuro.backup')
        counter = 1
        while backup_path.exists():
            backup_path = target_path.with_name(f"{target_path.stem}-{counter}.kubecuro.backup")
            counter += 1
        return backup_path

    def check_git_safety(self) -> List[str]:
        warnings = []
        gitignore = self.workspace / ".gitignore"
        if (self.workspace / ".git").exists() and gitignore.exists():
            try:
                content = gitignore.read_text(encoding='utf-8', errors='ignore')
                for ext in ["*.kubecuro.backup", "*.kubecuro.tmp"]:
                    if ext not in content:
                        warnings.append(f"Add '{ext}' to .gitignore")
            except: pass
        return warnings

    def _file_error(self, path: str, status: str, error: str) -> Dict[str, Any]:
        return {
            "file_path": path, "status": status, "error": error, 
            "success": False, "partial_heal": False, 
            "system_errors": error, "kind": "Unknown"
        }
