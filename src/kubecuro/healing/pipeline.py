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
        Initializes the pipeline with the necessary specialized units.
        
        Args:
            catalog: The distilled K8s JSON schema required for structural repair.
        """
        self.lexer = KubeLexer()
        self.scanner = KubeScanner()
        self.shadow = KubeShadow()
        self.structurer = KubeStructurer(catalog)

    def run(self, input_text: str) -> HealContext:
        """
        Executes the 'ER' (Emergency Room) sequence. 
        
        Args:
            input_text: The raw, potentially traumatized YAML string.
            
        Returns:
            HealContext: A fully populated context object ready for Shielding/Validation.
        """
        
        # --- PHASE 1: LEXICAL REPAIR ---
        # Cleans character-level garbage (UTF-8 BOM, invisible artifacts).
        cleaned_text = self.lexer.repair(input_text)

        # --- PHASE 2: SHADOW CAPTURE ---
        # Snapshots comments and positioning before we dismantle the text.
        self.shadow.capture(cleaned_text)

        # --- PHASE 3: INTENT EXTRACTION (SCANNING) ---
        # Extracts shards and discovers identity (Kind/ApiVersion).
        shards = self.scanner.scan(cleaned_text)
        kind, api = self.scanner.get_identity()

        # --- PHASE 4: INITIALIZATION OF CONTEXT ---
        # Building the state object that tracks the file's progress.
        context = HealContext(
            raw_text=cleaned_text,
            shards=shards,
            shadow_map=self.shadow,
            kind=kind,
            api_version=api
        )

        # --- PHASE 5: HEURISTIC RECONSTRUCTION ---
        # The Structurer uses the catalog to fix hierarchy and indentation.
        # Note: structurer.reconstruct internal updates context.reconstructed_docs
        self.structurer.reconstruct(context)

        return context
