#!/usr/bin/env python3
"""
KUBECURO STRUCTURER - Comment-Aware & Multi-Doc Reconstruction
--------------------------------------------------------------
This module transforms flat Lexer shards into hierarchical trees.
It uses a stack-based approach to rebuild the YAML structure while
supporting multiple Kubernetes documents within a single file.

Author: Nishar A Sunkesala / KubeCuro Team
Date: 2026-01-16
"""

from typing import Any, Dict, List, Optional
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from kubecuro.healing.context import HealContext

class KubeStructurer:
    """
    The Architect: Rebuilds the YAML tree from identified shards.
    Uses the K8s catalog to enforce correct types (arrays vs objects)
    and handles multiple documents separated by '---'.
    """

    def __init__(self, catalog: Dict[str, Any]):
        """
        Initializes the structurer with a reference schema.
        
        Args:
            catalog: The distilled K8s API schema used to determine field types.
        """
        self.catalog = catalog

    def reconstruct(self, context: HealContext) -> List[CommentedMap]:
        """
        Translates Lexer shards into a list of comment-preserving CommentedMaps.
        Updates the context with the final reconstructed documents.
        """
        all_documents = []
        current_shards = []

        # Step 1: Split shards into groups based on the '---' separator
        for shard in context.shards:
            if shard.key == "---":
                if current_shards:
                    all_documents.append(self._build_tree(current_shards, context.kind))
                    current_shards = []
            else:
                current_shards.append(shard)
        
        # Add the final (or only) document
        if current_shards:
            all_documents.append(self._build_tree(current_shards, context.kind))

        # Store back in context for the Exporter and Engine
        context.reconstructed_docs = all_documents
        return all_documents

    def _build_tree(self, shards: List[Any], default_kind: str) -> CommentedMap:
        """
        The core stack-based reconstruction logic for a single YAML document.
        Handles the distinction between Maps, Sequences, and Leaf nodes.
        """
        rebuilt_tree = CommentedMap()
        
        # 1. Identity Detection (Contextual Kind)
        doc_kind = default_kind
        for s in shards:
            if s.key == "kind" and s.value:
                doc_kind = s.value
                break
        
        # Safe lookup in catalog; default to empty dict if kind unknown
        kind_schema = self.catalog.get(doc_kind, {})
        
        # 2. Stack Setup: [(indent_level, container_ref, schema_node, is_in_list)]
        # Indent -1 is the root of the document
        stack = [(-1, rebuilt_tree, kind_schema, False)]

        for shard in shards:
            # Handle closing of nested scopes (Popping the stack)
            while len(stack) > 1 and shard.indent <= stack[-1][0]:
                stack.pop()

            parent_indent, parent_container, parent_schema, is_in_list = stack[-1]

            # 3. Catalog Lookup for the current key
            # Safely navigate the schema nested structure
            field_info = {}
            if parent_schema and "fields" in parent_schema:
                field_info = parent_schema["fields"].get(shard.key, {})
            
            field_type = field_info.get("type")

            # 4. Handle List Item Indicators ('- key: value')
            # If the shard is a list item, ensure we are inside a CommentedSeq
            if shard.is_list_item:
                if not isinstance(parent_container, CommentedSeq):
                    # Fallback: if schema didn't predict a list, force one
                    new_seq = CommentedSeq()
                    parent_container[shard.key] = new_seq
                    target_container = CommentedMap()
                    new_seq.append(target_container)
                else:
                    # Current container is already a list, add a new map entry
                    target_container = CommentedMap()
                    parent_container.append(target_container)
            else:
                target_container = parent_container

            # 5. Type-Specific Insertion
            if field_type == "array":
                # Prepare a sequence for the children to inhabit
                new_seq = CommentedSeq()
                target_container[shard.key] = new_seq
                
                # Push the sequence to the stack
                stack.append((shard.indent, new_seq, field_info, True))

            elif field_type == "object" or (shard.value is None and not shard.is_list_item):
                # Prepare a nested map
                new_map = CommentedMap()
                target_container[shard.key] = new_map
                
                # Attach start comments if they exist
                if shard.comment:
                    new_map.yaml_set_start_comment(shard.comment)
                
                stack.append((shard.indent, new_map, field_info, False))

            else:
                # Leaf Node Assignment (Key: Value)
                val = self._clean_value(shard.value)
                target_container[shard.key] = val
                
                # Attach end-of-line comments if they exist
                if shard.comment:
                    target_container.yaml_add_eol_comment(shard.comment, key=shard.key)

        return rebuilt_tree

    def _clean_value(self, val: Any) -> Any:
        """Strips quotes and normalizes types from the Lexer."""
        if isinstance(val, str):
            val = val.strip()
            # Remove wrapping quotes often found in corrupted YAML
            if (val.startswith("'") and val.endswith("'")) or \
               (val.startswith('"') and val.endswith('"')):
                return val[1:-1]
        return val
