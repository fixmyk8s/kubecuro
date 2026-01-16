#!/usr/bin/env python3
"""
KUBECURO TEST SUITE - Integration Verification
----------------------------------------------
Tests the interaction between the HealingPipeline and ShieldEngine
to ensure structural repair and policy enforcement are functional.

Author: KubeCuro Team
Date: 2026-01-16
"""

import json
from kubecuro.healing.pipeline import HealingPipeline
from kubecuro.rules.shield import ShieldEngine

def run_stress_test():
    # 1. Mock Schema Catalog (Minimal for testing)
    mock_catalog = {
        "Deployment": {
            "required": ["apiVersion", "kind", "metadata", "spec"],
            "properties": {"spec": {"type": "object"}}
        }
    }

    # 2. Corrupted Input Manifest
    # Note: Intentional bad indentation and missing critical blocks
    corrupted_yaml = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-smoketest
spec:
  template:
    spec:
      containers:
      - name: nginx
        image: nginx:latest
    """

    print("--- [PHASE 1: HEALING] ---")
    pipeline = HealingPipeline(mock_catalog)
    context = pipeline.run(corrupted_yaml)
    
    healed_doc = context.reconstructed_docs[0]
    print(f"Healed Kind: {context.kind}")
    print(f"Healed API: {context.api_version}")

    print("\n--- [PHASE 2: SHIELDING] ---")
    shield = ShieldEngine(cpu_limit="200m", mem_limit="256Mi")
    protected_doc, logs = shield.protect(healed_doc)

    for log in logs:
        print(f"Shield Log: {log}")

    # 3. Assertions
    print("\n--- [PHASE 3: VALIDATION] ---")
    has_namespace = "namespace" in protected_doc.get("metadata", {})
    has_limits = "limits" in protected_doc["spec"]["template"]["spec"]["containers"][0].get("resources", {})

    if has_namespace and has_limits:
        print("RESULT: SUCCESS - Pipeline and Shield are 100% Integrated.")
    else:
        print("RESULT: FAILURE - Missing Logic Gates.")

if __name__ == "__main__":
    run_stress_test()
