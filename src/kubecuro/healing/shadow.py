#!/usr/bin/env python3
"""
KUBECURO SHADOW - The Intent Curator
------------------------------------
Records comments and formatting metadata to preserve developer 
documentation during structural reconstruction. 

This version utilizes quote-aware comment detection to prevent 
data-loss in values containing '#' symbols.

Author: Nishar A Sunkesala / KubeCuro Team
Date: 2026-01-16
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class ShadowMetadata:
    """
    Stores human-readable annotations associated with a specific YAML line.
    """
    above_comments: List[str] = field(default_factory=list)
    inline_comment: Optional[str] = None

class KubeShadow:
    """
    The Curator: Captures the 'Shadow' of the manifest—the parts 
    that aren't functional data but are vital for human maintenance.
    """
    def __init__(self):
        # Maps original line numbers to their respective metadata
        self.comment_map: Dict[int, ShadowMetadata] = {}
        # Stores comments found at the very end of a file with no data line following
        self.orphans: List[str] = []

    def _find_safe_comment_idx(self, text: str) -> int:
        """
        Identifies the true start of a comment, protecting hashes 
        wrapped in quotes. Matches the Lexer's surgical logic.
        """
        in_double = in_single = escaped = False
        for i, char in enumerate(text):
            if escaped:
                escaped = False
                continue
            if char == '\\':
                escaped = True
                continue
            if char == '"' and not in_single:
                in_double = not in_double
            elif char == "'" and not in_double:
                in_single = not in_single
            if char == '#' and not in_double and not in_single:
                # Valid YAML comments require a leading space if not at start
                if i == 0 or text[i-1].isspace():
                    return i
        return -1

    def capture(self, raw_text: str):
        """
        Scans the repaired text to map comments to their logical data lines.
        
        Args:
            raw_text: The string output from the Lexer repair phase.
        """
        lines = raw_text.splitlines()
        pending_comments = []

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # 1. Full-Line Comment Detection
            if stripped.startswith('#'):
                pending_comments.append(line)
                continue

            # 2. Skip Empty Lines (but keep pending comments alive)
            if not stripped:
                continue

            # 3. Data Line Association & Inline Capture
            inline_part = None
            comment_idx = self._find_safe_comment_idx(line)
            
            if comment_idx != -1:
                inline_part = line[comment_idx:].strip()

            # 4. Commit to Map
            if pending_comments or inline_part:
                self.comment_map[i] = ShadowMetadata(
                    above_comments=pending_comments.copy(),
                    inline_comment=inline_part
                )
                pending_comments.clear()

        # Any comments left over at the end of the file are orphans
        self.orphans = pending_comments

    def get_metadata(self, line_no: int) -> Optional[ShadowMetadata]:
        """
        Retrieves metadata for a specific line. Used by the Structurer 
        to re-attach comments to the new tree.
        """
        return self.comment_map.get(line_no)
