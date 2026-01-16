#!/usr/bin/env python3
"""
KUBECURO HEALING PIPELINE - The Chief Surgeon
---------------------------------------------
This is the central coordinator for the 'Emergency Room' phase. 
It ensures that raw text is processed in a strict, idempotent sequence 
to preserve user intent (comments/formatting) while repairing structural damage.

The pipeline transforms raw, corrupted text into a structured 'HealContext',
which serves as the complete medical record for the Structurer to use.

Author: Nishar A Sunkesala / KubeCuro Team
Date: 2026-01-16
"""

from typing import Optional, List, Any
from dataclasses import dataclass, field

# Modular components of the healing suite
from kubecuro.healing.lexer import KubeLexer
from kubecuro.healing.scanner import KubeScanner
from kubecuro.healing.shadow import KubeShadow
from kubecuro.healing.structurer import KubeStructurer
from kubecuro.core.models import Shard
from kubecuro.healing.context import HealContext

class HealingPipeline:
    """
    The Orchestrator: Ensures that lexical repair, metadata capture, 
    and intent extraction happen in a strictly defined order.
    """

    def __init__(self, catalog: dict):
        """
        Initializes the pipeline with specialized diagnostic and surgical units.
        
        Args:
            catalog: The distilled K8s JSON schema required for structural repair.
        """
        self.lexer = KubeLexer()
        self.scanner = KubeScanner()
        self.shadow = KubeShadow()
        self.structurer = KubeStructurer(catalog)

    def run(self, input_text: str) -> HealContext:
        """
        Executes the 'ER' (Emergency Room) sequence to stabilize and repair manifests.
        Each phase builds upon the last, culminating in a reconstructed K8s object.
        """
        
        # --- PHASE 1: LEXICAL REPAIR & SHARDING ---
        # FIX: Lexer doesn't have .repair(), it has .shard() which 
        # internally calls .repair_line() for character-level cleanup.
        shards = self.lexer.shard(input_text)
        
        # Reconstruct cleaned text from shards for the shadow map.
        # This ensures the 'Shadow' sees the text exactly as the Lexer repaired it,
        # ensuring UTF-8 BOM/artifacts removed during sharding are reflected.
        cleaned_text = "\n".join([s.raw_line for s in shards])

        # --- PHASE 2: SHADOW CAPTURE ---
        # Captures the original formatting state (indentation patterns, comment placement)
        # so that the Structurer can re-apply 'flavor' to the final output.
        self.shadow.capture(cleaned_text)

        # --- PHASE 3: INTENT EXTRACTION (SCANNING) ---
        # The scanner identifies the 'Identity' of the manifest (Kind/APIVersion).
        # We capture found_shards to maintain compatibility with the Scanner API,
        # though we prioritize the Lexer's shards for the final context.
        found_shards = self.scanner.scan(cleaned_text) 
        kind, api = self.scanner.get_identity()

        # --- PHASE 4: INITIALIZATION OF CONTEXT ---
        # The HealContext acts as the 'Medical Record' for the document.
        # It carries all state discovered during diagnostic phases.
        context = HealContext(
            raw_text=cleaned_text,
            shards=shards, # Pass the shards generated in Phase 1
            shadow_map=self.shadow,
            kind=kind,
            api_version=api
        )

        # --- PHASE 5: HEURISTIC RECONSTRUCTION ---
        # The Structurer uses the context and the Schema Catalog to perform 
        # surgical repair, filling in missing structural gaps while 
        # maintaining the user's original comment intent.
        self.structurer.reconstruct(context)

        return context
