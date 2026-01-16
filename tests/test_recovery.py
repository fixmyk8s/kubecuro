import json
import os
import sys

# Ensure the 'src' directory is in the python path so we can import kubecuro
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from kubecuro.healing.pipeline import HealingPipeline
from kubecuro.healing.structurer import KubeStructurer

def run_demonstration():
    # 1. Setup paths - looking for catalog in ../catalog/
    base_dir = os.path.dirname(os.path.abspath(__file__))
    catalog_path = os.path.join(base_dir, "..", "catalog", "k8s_v1_distilled.json")

    # Load the Blueprint
    with open(catalog_path, 'r') as f:
        catalog = json.load(f)

    # 2. The "Nightmare" YAML
    broken_yaml = """
# Critical Production Service
kind: Service
metadata:
name: web-backend
spec:
ports:
port:80
targetPort: 8080
    """
    broken1_yaml = """
    kind: Service
    metadata:
      name: web-backend
    spec:
      ports:
        port: 80
        targetPort: 8080
        """
    pipeline = HealingPipeline()
    context = pipeline.run(broken1_yaml)

    surgeon = KubeStructurer(catalog)
    healed_dict = surgeon.reconstruct(context)

    print("-" * 30)
    print("HEALED RECONSTRUCTION:")
    print(json.dumps(healed_dict, indent=2))
    print("-" * 30)

    # Check for the list recovery
    if isinstance(healed_dict.get("spec", {}).get("ports"), list):
        print("✅ SUCCESS: Structural inference recovered the list!")
    else:
        print("❌ FAILURE: Structural inference failed.")

if __name__ == "__main__":
    run_demonstration()
