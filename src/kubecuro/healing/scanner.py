#!/usr/bin/env python3
"""
KUBECURO SCANNER - The Archeologist (Phase 1.2)
-----------------------------------------------
Mines identity and structural 'shards' from potentially non-compliant 
YAML text. Uses regex to recover data from high-trauma lines.

Author: Nishar A Sunkesala / KubeCuro Team
Date: 2026-01-16
"""

import re
from typing import List, Tuple, Optional
from kubecuro.core.models import Shard

class KubeScanner:
    """
    Identifies Kubernetes resources and extracts semantic meaning 
    from raw lines. Acts as a second-pass validator for the Lexer.
    """
    
    # Restored: The established Regex to catch keys even with weird formatting.
    # Group 1: Indent, Group 2: List dash, Group 3: Key, Group 4: Value
    LINE_PATTERN = re.compile(r'^(\s*)(?:(-\s*))?([\w\.\-\/]+)\s*:\s*(.*)$')
    
    def __init__(self):
        # State tracking for the manifest identity
        self.found_kind: Optional[str] = None
        self.found_api: Optional[str] = None

    def scan(self, raw_text: str) -> List[Shard]:
        """
        Processes text into Shards using established regex patterns.
        Ensures alignment with the current models.py.
        """
        # --- RESET GATE ---
        # Ensures batch processing doesn't leak 'Kind' from previous files
        self.found_kind = None
        self.found_api = None
        
        shards = []
        lines = raw_text.splitlines()
        
        for i, line in enumerate(lines, 1):
            # 1. Skip logic (Shadow.py handles comments/blanks)
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue

            match = self.LINE_PATTERN.match(line)
            if match:
                indent_str, list_prefix, key, value = match.groups()
                
                # Restoration of established cleanup logic
                clean_value = value.strip() if value else None
                
                # Identity Discovery: Updates internal state for Pipeline use
                if key == "kind" and clean_value:
                    self.found_kind = self._clean_id(clean_value)
                if key == "apiVersion" and clean_value:
                    self.found_api = self._clean_id(clean_value)

                # Map to current models.py Shard (using is_list_item, not is_list_start)
                shards.append(Shard(
                    line_no=i,
                    indent=len(indent_str),
                    key=key,
                    value=clean_value,
                    is_list_item=(list_prefix is not None),
                    raw_line=line
                ))
            else:
                # Restored: Logic for lines that aren't key:value (like list scalars)
                shards.append(self._handle_anomaly(i, line))
                
        return shards

    def _handle_anomaly(self, line_no: int, line: str) -> Shard:
        """Handles list scalars or dangling values that regex missed."""
        stripped = line.lstrip()
        is_list = stripped.startswith('-')
        content = stripped[1:].lstrip() if is_list else stripped
        
        return Shard(
            line_no=line_no,
            indent=len(line) - len(line.lstrip()),
            key="",  # No key found for this line
            value=content,
            is_list_item=is_list,
            raw_line=line
        )

    def _clean_id(self, val: str) -> str:
        """Strips quotes from found identity markers."""
        return val.strip().strip("'").strip('"')

    def get_identity(self) -> Tuple[Optional[str], Optional[str]]:
        """Provides the discovered resource identity to the Engine."""
        return self.found_kind, self.found_api
