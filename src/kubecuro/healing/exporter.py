#!/usr/bin/env python3
"""
KUBECURO EXPORTER - High-Fidelity Round-Trip
--------------------------------------------
Author: Nishar A Sunkesala / KubeCuro Team
Date: 2026-01-16
"""

import io
from typing import Any, Dict, List, Union
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from kubecuro.healing.pipeline import HealContext

class KubeExporter:
    """
    The Reconstructor: Converts healed CommentedMaps back to YAML strings.
    """
    
    def __init__(self):
        self.yaml = YAML(typ='rt')
        self.yaml.preserve_quotes = True
        # Standard K8s: 2 spaces, but sequences are indented 4 (offset 2)
        # for maximum readability in IDEs.
        self.yaml.indent(mapping=2, sequence=4, offset=2)
        self.yaml.width = 4096 
        self.preferred_order = ["apiVersion", "kind", "metadata", "spec", "data", "status"]

    def _get_sorted_map(self, data: Any) -> Any:
        """
        Recursively sorts keys while maintaining comments and list stability.
        """
        if not isinstance(data, CommentedMap):
            return data

        sorted_map = CommentedMap()
        
        # 1. Preserve Header Comments
        if hasattr(data, 'ca') and data.ca.comment:
            sorted_map.ca.comment = data.ca.comment

        # 2. Key Sorting Logic
        keys = list(data.keys())
        def sort_logic(key):
            if key in self.preferred_order:
                return self.preferred_order.index(key)
            # Unknown keys keep their relative original position
            return len(self.preferred_order) + keys.index(key)
        
        sorted_keys = sorted(keys, key=sort_logic)

        # 3. Recursive Rebuild
        for key in sorted_keys:
            value = data[key]
            
            if isinstance(value, CommentedMap):
                value = self._get_sorted_map(value)
            elif isinstance(value, list):
                # Stability Check: ensure list items (like env vars) aren't scrambled
                value = [self._get_sorted_map(item) if isinstance(item, CommentedMap) else item for item in value]
            
            sorted_map[key] = value
            
            # 4. Transfer Comment Metadata (EOL and Inline)
            if hasattr(data, 'ca') and key in data.ca.items:
                sorted_map.ca.items[key] = data.ca.items[key]

        return sorted_map

    def export(self, healed_data: Union[CommentedMap, List[CommentedMap]], context: HealContext) -> str:
        """
        Exports data into a single string. Includes explicit doc separators for multi-doc.
        """
        stream = io.StringIO()
        
        # Ensure we always treat input as a list for consistent processing
        docs = healed_data if isinstance(healed_data, list) else [healed_data]
        
        for i, doc in enumerate(docs):
            if not doc: continue
            
            ordered_doc = self._get_sorted_map(doc)
            
            # For multi-document files, we explicitly write the separator
            if i > 0:
                stream.write("---\n")
                
            self.yaml.dump(ordered_doc, stream)
            
        return stream.getvalue()
