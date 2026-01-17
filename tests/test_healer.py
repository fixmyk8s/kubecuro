import pytest
from pathlib import Path
from kubecuro.healing.pipeline import HealingPipeline
from ruamel.yaml import YAML
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

def test_full_chaos_healing():
    """
    TORTURE TEST: Ensures extreme edge cases are healed 
    enough for a standard YAML parser to load the result.
    """
    chaos_path = Path(__file__).parent / "chaos_manifest.yaml"
    pipeline = HealingPipeline()
    
    result = pipeline.heal_manifest(file_path=chaos_path, force_write=True)
    
    assert result["success"] is True, f"Healing failed with status: {result['status']}"
    assert result["partial_heal"] is True or result["status"] in ["STRUCTURE_OK", "MULTI_DOC_HANDLED"]
    
    # Validation via ruamel
    yaml_parser = YAML(typ='safe')
    try:
        raw_docs = list(yaml_parser.load_all(result["content"]))
        parsed_docs = [doc for doc in raw_docs if doc is not None]
        assert len(parsed_docs) > 0
        assert "apiVersion" in parsed_docs[0]
    except Exception as e:
        pytest.fail(f"Healed YAML is still unparseable: {e}")

def test_noop_idempotency():
    """
    IDEMPOTENCY TEST: Ensures that a perfectly valid manifest
    is not altered semantically or structurally.
    """
    # Standardized 2-space indentation
    perfect_yaml = (
        "apiVersion: v1\n"
        "kind: Service\n"
        "metadata:\n"
        "  name: web-svc\n"
        "spec:\n"
        "  selector:\n"
        "    app: web\n"
    )

    pipeline = HealingPipeline()
    result = pipeline.heal_manifest(raw_content=perfect_yaml)
    
    # 1. Pipeline Success
    assert result["success"] is True
    
    # 2. Semantic Check (Data integrity)
    yaml_parser = YAML(typ='safe')
    original_data = list(yaml_parser.load_all(perfect_yaml))
    healed_data = list(yaml_parser.load_all(result["content"]))
    assert original_data == healed_data, "The actual K8s data was altered!"
    
    # 3. Structural Check (Character identity)
    # We strip both to ignore trailing newline differences
    assert result["content"].strip() == perfect_yaml.strip(), "Healer modified formatting/whitespace!"
    
    # 4. Metadata Assertions
    assert result["semantic_preserved"] is True
    assert result["original_parseable"] is True
    assert result["doc_count"] == 1
    assert result["report"]["lines_changed"] == 0, "Report should show exactly 0 changes"

if __name__ == "__main__":
    pytest.main([__file__])
