#!/usr/bin/env python3
"""
KUBECURO VALIDATOR - The Judge
------------------------------
The Validator is the final safety gate in the KubeCuro pipeline. 
It performs a "Pre-Flight" validation on reconstructed objects against 
the K8s API schema before the Engine allows them to be written to disk.

Author: Nishar A Sunkesala / KubeCuro Team
Date: 2026-01-16
"""

from typing import Dict, Any, Tuple, List
import logging
from ruamel.yaml.comments import CommentedMap

# Standardized logging for audit trails
logger = logging.getLogger("kubecuro.validator")

class KubeValidator:
    """
    Enforces schema integrity on healed manifests.
    Provides the 'Self-Abort' signal if a healed version fails 
    fundamental Kubernetes structural requirements.
    """

    def __init__(self, catalog: Dict[str, Any]):
        """
        Initializes the validator using the distilled K8s OpenAPI catalog.
        
        Args:
            catalog: The minified JSON schema map from the catalog/ directory.
        """
        self.catalog = catalog
        # Core fields that must exist in every single K8s resource
        self.required_fields = ["apiVersion", "kind", "metadata"]

    def validate_reconstruction(self, doc: Any, strict: bool = False) -> Tuple[bool, str]:
        """
        The primary integrity check. Validates that the reconstructed 
        dictionary is a viable Kubernetes resource.
        """
        if not isinstance(doc, (dict, CommentedMap)):
            return False, "Aborting: Healed content is not a valid dictionary structure."

        # --- TEST 1: Identity & Metadata Presence ---
        for field in self.required_fields:
            if field not in doc:
                return False, f"Validation Failed: Missing required top-level field '{field}'."

        kind = doc.get("kind")
        
        # --- TEST 2: Catalog Knowledge & Deep Validation ---
        schema = self.catalog.get(kind)
        if not schema:
            return True, f"Warning: Kind '{kind}' is outside local catalog. Basic validation only."

        # Perform recursive structural check, passing the strict flag
        return self._deep_validate(doc, schema, strict=strict)

    def _deep_validate(self, doc: Any, schema: Dict[str, Any], path: str = "", strict: bool = False) -> Tuple[bool, str]:
        """
        Recursively checks that the 'surgery' matches the K8s API expectations.
        Now properly handles the 'strict' flag for typo detection.
        """
        # Check required fields defined in the schema for this level
        for req in schema.get("required", []):
            if req not in doc:
                return False, f"Structural Error: Field '{path + req}' is required but missing."

        schema_fields = schema.get("fields", {})
        for key, value in doc.items():
            field_info = schema_fields.get(key)
            
            # Typo / Unknown Field Detection
            if not field_info:
                if strict:
                    return False, f"Strict Mode Violation: Unknown field '{path + key}'. Possible typo?"
                continue 

            expected_type = field_info.get("type")
            
            # Type Validation: Object
            if expected_type == "object":
                if not isinstance(value, (dict, CommentedMap)):
                    return False, f"Logic Error: '{path + key}' must be a map/object."
                # PASSING STRICT DOWN RECURSIVELY
                valid, err = self._deep_validate(value, field_info, path=f"{path}{key}.", strict=strict)
                if not valid: return False, err

            # Type Validation: Array
            elif expected_type == "array":
                if not isinstance(value, list):
                    return False, f"Logic Error: '{path + key}' must be a list/sequence."
                
                # Check list items if schema provided
                item_schema = field_info.get("items")
                if item_schema and value and isinstance(value[0], (dict, CommentedMap)):
                    # PASSING STRICT DOWN RECURSIVELY
                    valid, err = self._deep_validate(value[0], item_schema, path=f"{path}{key}[0].", strict=strict)
                    if not valid: return False, err

        return True, "Manifest passes structural integrity check."

    def compare_health(self, original_status: str, healed_doc: Dict[str, Any]) -> int:
        """
        Calculates a confidence score (0-100) based on improvement.
        Established in Phase 1 Roadmap.
        """
        score = 50 
        is_valid, _ = self.validate_reconstruction(healed_doc)
        
        if is_valid:
            score += 30
        
        # Identity bonus
        if healed_doc.get("kind") and healed_doc.get("apiVersion"):
            score += 20
            
        return min(score, 100)
