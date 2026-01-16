#!/usr/bin/env python3
"""
KUBECURO STRUCTURER - Comment-Aware & Multi-Doc Reconstruction
--------------------------------------------------------------
Transforms flat Lexer shards into hierarchical trees using a 
stack-based approach and the K8s OpenAPI catalog. Aligned with 
the 2026-01-16 Shard model.

Author: Nishar A Sunkesala / KubeCuro Team
Date: 2026-01-16
"""

from typing import Any, Dict, List, Optional, Tuple
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from kubecuro.healing.context import HealContext

class KubeStructurer:
    """
    The Architect: Rebuilds the YAML tree from identified shards.
    Uses a stack-based state machine to handle indentation depth
    and schema-driven type enforcement.
    """

    def __init__(self, catalog: Dict[str, Any]):
        """
        Initializes the structurer with the K8s schema catalog.
        
        Args:
            catalog: Distilled K8s API schema (e.g., {'Pod': {'fields': {...}}})
        """
        self.catalog = catalog

    def reconstruct(self, context: HealContext) -> List[CommentedMap]:
        """
        Processes shards from the context and rebuilds one or more 
        CommentedMap objects (supporting multi-document YAML).
        """
        all_documents = []
        current_shards = []

        # Phase 1: Split into logical documents by '---'
        for shard in context.shards:
            if shard.key == "---":
                if current_shards:
                    all_documents.append(self._build_tree(current_shards, context.kind))
                    current_shards = []
            else:
                current_shards.append(shard)
        
        # Add final document segment
        if current_shards:
            all_documents.append(self._build_tree(current_shards, context.kind))

        # Update context for the Exporter/Shield phases
        context.reconstructed_docs = all_documents
        return all_documents

    def _build_tree(self, shards: List[Any], default_kind: str) -> CommentedMap:
        """
        Core Reconstruction Engine: Uses a stack to track parent-child
        relationships based on indentation and schema types.
        """
        rebuilt_tree = CommentedMap()
        
        # 1. Determine the "Truth Source" (Kind) for this specific document
        doc_kind = default_kind
        for s in shards:
            if s.key == "kind" and s.value:
                doc_kind = str(s.value)
                break
        
        # Get schema node for this Kind, fallback to empty dict if unknown
        kind_schema = self.catalog.get(doc_kind, {"fields": {}})
        
        # 2. Stack: (indent, container_ref, schema_node)
        # Root is at indent -1
        stack = [(-1, rebuilt_tree, kind_schema)]

        for shard in shards:
            # --- SCOPE MANAGEMENT ---
            # Pop stack until we find the parent of the current indent level
            while len(stack) > 1 and shard.indent <= stack[-1][0]:
                stack.pop()

            parent_indent, parent_container, parent_schema = stack[-1]

            # --- SCHEMA LOOKUP ---
            field_info = {}
            if parent_schema and "fields" in parent_schema:
                field_info = parent_schema["fields"].get(shard.key, {})
            
            field_type = field_info.get("type", "string")

            # --- CONTAINER RESOLUTION ---
            # Determine where the data goes: straight to parent or into a new list item
            if shard.is_list_item:
                target_container = self._ensure_list_item(parent_container, shard.key)
            else:
                target_container = parent_container

            # --- INSERTION & NESTING ---
            if field_type == "array":
                # Create a sequence and push to stack
                new_seq = CommentedSeq()
                target_container[shard.key] = new_seq
                stack.append((shard.indent, new_seq, field_info))
                
            elif field_type == "object" or (shard.value is None and not shard.is_list_item):
                # Create a map and push to stack
                new_map = CommentedMap()
                target_container[shard.key] = new_map
                
                # Apply 'Start' comments (above the block)
                if shard.comment:
                    new_map.yaml_set_start_comment(shard.comment)
                
                stack.append((shard.indent, new_map, field_info))
            
            else:
                # Leaf Node (Standard Key/Value)
                clean_val = self._clean_value(shard.value)
                
                # Handling for anonymous list items (e.g., "- nginx")
                if not shard.key and isinstance(target_container, CommentedSeq):
                    target_container.append(clean_val)
                else:
                    target_container[shard.key] = clean_val
                    
                # Apply 'EOL' comments (to the right of the value)
                if shard.comment and hasattr(target_container, "yaml_add_eol_comment"):
                    try:
                        target_container.yaml_add_eol_comment(shard.comment, key=shard.key)
                    except: pass # Protect against non-mappable containers

        return rebuilt_tree

    def _ensure_list_item(self, parent: Any, key: str) -> Any:
        """
        Ensures the parent is a sequence and returns the active map within it.
        This handles the '- key: value' syntax.
        """
        if not isinstance(parent, CommentedSeq):
            # If the schema didn't expect a list but we found a '-', 
            # we force a sequence to prevent data loss.
            new_seq = CommentedSeq()
            if key:
                parent[key] = new_seq
            return parent # Return parent as the hook
        
        # Add new map entry to existing list
        new_entry = CommentedMap()
        parent.append(new_entry)
        return new_entry

    def _clean_value(self, val: Any) -> Any:
        """Strips syntax artifacts and normalizes types."""
        if val is None: return None
        if isinstance(val, str):
            val = val.strip()
            # Unquote strings if they were wrapped during corruption
            if (val.startswith("'") and val.endswith("'")) or \
               (val.startswith('"') and val.endswith('"')):
                return val[1:-1]
            # Boolean/Int auto-casting fallback
            if val.lower() == "true": return True
            if val.lower() == "false": return False
            try:
                if "." in val: return float(val)
                return int(val)
            except ValueError:
                pass
        return val
