import pytest
from pathlib import Path
from kubecuro.healing.pipeline import HealingPipeline

def test_full_chaos_healing():
    """
    TORTURE TEST: Ensures extreme edge cases are healed 
    enough for a standard YAML parser to load the result.
    """
    # 1. Setup
    chaos_path = Path(__file__).parent / "chaos_manifest.yaml"
    pipeline = HealingPipeline()
    
    # 2. Execute Healing with force_write=True
    # This enables the aggressive logic we just added to the pipeline
    result = pipeline.heal_manifest(file_path=chaos_path, force_write=True)
    
    # 3. Assertions
    # We now check that success is True (because force_write was used)
    assert result["success"] is True, f"Healing failed with status: {result['status']}"
    
    # Verify that the healer actually detected and fixed things
    assert result["partial_heal"] is True or result["status"] == "STRUCTURE_OK"
    assert result["phase1_complete"] is True
    
    # Verify report accuracy
    report = result["report"]
    assert report["lines_changed"] > 0, "Healer claimed no changes were needed on a broken file!"
    
    # 4. Final Validation: The "Gold Standard" test
    from ruamel.yaml import YAML
    yaml = YAML()
    try:
        # Change yaml.load() to list(yaml.load_all())
        # This handles manifests with '---' separators
        parsed_docs = list(yaml.load_all(result["content"]))
        
        # Verify we actually recovered documents
        assert len(parsed_docs) > 0, "Healer returned an empty stream"
        assert parsed_docs[0] is not None
        
        # Optional: Print how many docs were healed
        print(f"\nSuccessfully healed {len(parsed_docs)} Kubernetes documents.")
        
    except Exception as e:
        pytest.fail(f"Healed YAML is still unparseable: {e}")

if __name__ == "__main__":
    pytest.main([__file__])
