#!/usr/bin/env python3
"""
KUBECURO CORE MODELS
--------------------
Defines the fundamental data structures used across the KubeCuro engine.
These models represent the lowest level of manifest abstraction.

Author: Nishar A Sunkesala / KubeCuro Team
Date: 2026-01-16
"""

from dataclasses import dataclass
from typing import Optional, Any

@dataclass
class Shard:
    """
    The atomic unit of a Kubernetes manifest.
    
    A Shard represents a single logical line or key-value pair extracted 
    from the raw YAML text during the Lexing phase.
    """
    line_no: int            # The original line number in the source file
    indent: int             # The calculated indentation depth (whitespace count)
    key: str                # The YAML key (e.g., 'apiVersion', 'image')
    value: Optional[Any] = None  # The scalar value (string, int, bool) or None
    is_list_item: bool = False   # True if the line starts with a '-' indicator
    comment: Optional[str] = None # Captures inline or end-of-line # comments
    raw_line: str = ""      # The original unmutated string for recovery/debugging
