#!/usr/bin/env python3
"""
KUBECURO LEXER - Semantic Sharder (Phase 1.1)
--------------------------------------------
Repairs raw YAML trauma and decomposes lines into semantic Shard models.
Aligned with core.models.Shard signature (2026-01-16).

Author: Nishar A Sunkesala / KubeCuro Team
Date: 2026-01-16
"""

import re
from typing import List, Tuple, Any, Optional
from kubecuro.core.models import Shard

class KubeLexer:
    """
    Orchestrates the transition from raw text to semantic Shards.
    Maintains block state (|, >) to ensure content inside literals is preserved.
    """

    def __init__(self):
        self.in_block = False
        self.block_indent = 0

    def _clean_artifacts(self, text: str) -> str:
        """
        Removes invisible UTF-8 BOM markers and standardized line endings.
        """
        # Remove Byte Order Mark if present
        text = text.lstrip('\ufeff')
        # Standardize CRLF to LF
        return text.replace('\r\n', '\n')

    def _find_comment_split(self, text: str) -> int:
        """Protects quotes and # symbols inside values."""
        in_double_quote = in_single_quote = escaped = False
        for i, char in enumerate(text):
            if escaped: escaped = False; continue
            if char == '\\': escaped = True; continue
            if char == '"' and not in_single_quote: in_double_quote = not in_double_quote
            elif char == "'" and not in_double_quote: in_single_quote = not in_single_quote
            if char == '#' and not in_double_quote and not in_single_quote:
                if i == 0 or text[i-1].isspace(): return i
        return -1

    def _extract_semantics(self, code_part: str) -> Tuple[str, Optional[Any], bool]:
        """
        Splits a repaired code string into YAML components.
        Example: "- image: nginx" -> ("image", "nginx", True)
        """
        clean = code_part.strip()
        if not clean:
            return "", None, False
            
        is_list = clean.startswith('-')
        if is_list:
            clean = clean[1:].lstrip()
            
        if ':' in clean:
            # Handle standard key: value pairs
            key_part, _, val_part = clean.partition(':')
            return key_part.strip(), val_part.strip() or None, is_list
        
        # If no colon, treat the whole part as a value (list scalar or partial)
        return "", clean, is_list

    def repair_line(self, line: str) -> Tuple[int, str, str]:
        """
        Surgically repairs a line and returns (indent, code, comment).
        """
        # 1. Cleaning & Tabs
        raw_line = line.replace('\t', '  ').rstrip()
        content = raw_line.lstrip()
        if not content:
            return 0, "", ""
        
        indent = len(raw_line) - len(content)

        # 2. Block Protection (Case 12/13)
        if self.in_block:
            if indent <= self.block_indent and (':' in content or content.startswith('-')):
                self.in_block = False
            else:
                return indent, content, ""

        # 3. Comment Separation
        split_idx = self._find_comment_split(raw_line)
        code_part = raw_line[:split_idx] if split_idx != -1 else raw_line
        comment_part = raw_line[split_idx:].lstrip('# ') if split_idx != -1 else None

        # 4. Surgical Fixes (Stuck Dash/Colon)
        code_part = code_part.lstrip()
        # Fix "-image" -> "- image"
        if code_part.startswith('-') and len(code_part) > 1 and code_part[1].isalpha():
            code_part = "- " + code_part[1:]
        
        # Fix "kind:Pod" -> "kind: Pod" (Protecting URLs/Image tags)
        if not re.search(r'image[:\s]*[a-zA-Z0-9/]', code_part):
            code_part = re.sub(r'(?<!http)(?<!https):(?!\s)([a-zA-Z])', r': \1', code_part)

        # 5. Update Block State
        if any(marker in code_part for marker in ['|', '>', '|-', '>-']):
            self.in_block = True
            self.block_indent = indent

        return indent, code_part, comment_part

    def shard(self, raw_yaml: str) -> List[Shard]:
        """
        Decomposes raw YAML string into a List of Shard models.
        This is the primary interface for the HealingPipeline.
        """
        clean_yaml = self._clean_artifacts(raw_yaml)
        self.in_block = False
        lines = raw_yaml.splitlines()
        shards = []

        for i, original_line in enumerate(lines):
            working_line = original_line
            
            # Flush-Left Recovery Logic
            if i > 0 and lines[i-1].rstrip().endswith(':') and working_line.startswith('-'):
                p_indent = len(lines[i-1]) - len(lines[i-1].lstrip())
                working_line = (' ' * (p_indent + 2)) + working_line
            
            indent, code, comment = self.repair_line(working_line)
            key, value, is_list = self._extract_semantics(code)
            
            # Map directly to the user's models.py Shard dataclass
            shards.append(Shard(
                line_no=i + 1,
                indent=indent,
                key=key,
                value=value,
                is_list_item=is_list,
                comment=comment,
                raw_line=original_line
            ))
            
        return shards
