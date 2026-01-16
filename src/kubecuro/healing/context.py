#!/usr/bin/env python3
"""
KUBECURO HEALING CONTEXT
------------------------
A state-management object that acts as the 'Medical Record' for a manifest
undergoing repair. It stores both the raw trauma and the healed structures.

Author: Nishar A Sunkesala / KubeCuro Team
Date: 2026-01-16
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from kubecuro.core.models import Shard

@dataclass
class HealContext:
    """
    Maintains the state of a single manifest repair session.
    
    This object is initialized by the HealingPipeline and enriched by 
    the Lexer, Scanner, and Structurer sequentially.
    """
    raw_text: str                          # The initial raw input from the user
    shards: List[Shard] = field(default_factory=list) # List of processed Shard objects
    shadow_map: Any = None                 # Reference to the KubeShadow positioning map
    kind: Optional[str] = None             # The detected K8s Kind (e.g., Deployment)
    api_version: Optional[str] = None      # The detected K8s API Version
    reconstructed_docs: List[Any] = field(default_factory=list) # List of CommentedMaps
    cluster_version: str = "v1.31"         # Target K8s version for validation
    is_hardened: bool = False              # Flag indicating if security rules were applied
