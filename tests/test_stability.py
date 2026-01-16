import pytest
from pathlib import Path
from kubecuro.healing.pipeline import HealingPipeline
from ruamel.yaml import YAML

# Standardized K8s samples
VALID_K8S_SAMPLES = [
    "apiVersion: v1\nkind: Pod\nmetadata:\n  name: nginx\nspec:\n  containers:\n  - name: nginx\n    image: nginx",
    "apiVersion: v1\nkind: Service\nmetadata:\n  name: svc\nspec:\n  ports:\n  - port: 80\n    targetPort: 8080",
    "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: cfg\ndata:\n  conf: |\n    line1\n    line2",
    "apiVersion: rbac.authorization.k8s.io/v1\nkind: Role\nmetadata:\n  name: pod-reader\nrules:\n- apiGroups: ['']\n  resources: ['pods']\n  verbs: ['get', 'watch', 'list']",
    "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: dep\nspec:\n  selector:\n    matchLabels:\n      app: web\n  template:\n    metadata:\n      labels:\n        app: web\n    spec:\n      containers:\n      - name: web\n        image: web:latest",
]

@pytest.mark.parametrize("original_yaml", VALID_K8S_SAMPLES)
def test_stability_regression(original_yaml):
    """
    STABILITY TEST: Ensures that valid K8s patterns are 
    never corrupted by the healing pipeline.
    """
    pipeline = HealingPipeline()
    result = pipeline.heal_manifest(raw_content=original_yaml)
    
    # 1. Core Assertion: It must be successful
    assert result["success"] is True
    
    # 2. DATA INTEGRITY: The actual K8s objects must match
    yaml_parser = YAML(typ='safe')
    original_obj = list(yaml_parser.load_all(original_yaml))
    healed_obj = list(yaml_parser.load_all(result["content"]))
    
    # Filter out None from load_all
    original_obj = [d for d in original_obj if d is not None]
    healed_obj = [d for d in healed_obj if d is not None]
    
    assert original_obj == healed_obj, "CRITICAL: Healer altered valid K8s data!"
    
    # 3. SEMANTIC CHECK: The pipeline should recognize it's the same data
    # We allow formatting changes (lines_changed > 0) but demand semantic equivalence
    assert result["semantic_preserved"] is True, "Healer flagged semantic changes on valid file"

def test_bulk_directory_stability():
    """
    Run the healer against a directory of known good manifests.
    """
    manifest_dir = Path("tests/fixtures/valid_manifests")
    if not manifest_dir.exists():
        pytest.skip("No bulk manifest directory found at tests/fixtures/valid_manifests")
        
    pipeline = HealingPipeline()
    files = list(manifest_dir.glob("*.yaml"))
    
    for file_path in files:
        result = pipeline.heal_manifest(file_path=file_path)
        if not result["semantic_preserved"]:
            import json
            from ruamel.yaml import YAML
            y = YAML(typ='safe')
            orig = [d for d in list(y.load_all(file_path.read_text())) if d is not None]
            healed = [d for d in list(y.load_all(result["content"])) if d is not None]
            
            print(f"\n--- DEBUG: {file_path.name} ---")
            # This will show us the first key that differs
            print(f"ORIGINAL: {json.dumps(orig, sort_keys=True, indent=2)}")
            print(f"HEALED:   {json.dumps(healed, sort_keys=True, indent=2)}")
            
        assert result["success"] is True
        assert result["semantic_preserved"] is True
