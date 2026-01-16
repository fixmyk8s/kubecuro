#!/usr/bin/env python3
"""
KUBECURO LOGIC SHIELD - Policy Enforcement
------------------------------------------
The ShieldEngine acts as a 'Gatekeeper'. It evaluates parsed Kubernetes 
manifests against organizational standards and best practices, 
injecting missing fields or hardening configurations.

Author: Nishar A Sunkesala / KubeCuro Team
Date: 2026-01-16
"""

from typing import Dict, Any, List, Tuple
from ruamel.yaml.comments import CommentedMap

class ShieldEngine:
    """
    The 'Shield' Logic Library: 
    Responsible for enforcing operational standards. 
    It doesn't just fix broken text; it hardens the configuration.
    """
    
    def __init__(self, cpu_limit: str = "500m", mem_limit: str = "512Mi"):
        """
        Initializes the Shield with configurable baseline defaults.
        """
        self.default_cpu_limit = cpu_limit
        self.default_mem_limit = mem_limit
        
        # Registry of active rules to be executed against every document
        self.active_rules = [
            self._rule_ensure_namespace,
            self._rule_inject_resource_limits,
        ]

    def protect(self, doc: Any) -> Tuple[Any, List[str]]:
        """
        Runs the document through a gauntlet of safety checks.
        Returns the modified document and a list of human-readable changes.
        """
        changes = []
        
        # Safety check: only process dictionary-like objects
        if not isinstance(doc, (dict, CommentedMap)):
            return doc, []

        for rule in self.active_rules:
            # Each rule returns (modified_doc, log_message)
            doc, msg = rule(doc)
            if msg:
                changes.append(msg)
        
        return doc, changes

    def _rule_ensure_namespace(self, doc: Any) -> Tuple[Any, str]:
        """
        Policy: Every namespaced resource must have an explicit namespace.
        """
        kind = doc.get("kind", "")
        # Resources that should NOT have a namespace (Cluster-scoped)
        cluster_scoped = [
            "Namespace", "Node", "ClusterRole", "ClusterRoleBinding", 
            "StorageClass", "PersistentVolume", "CustomResourceDefinition"
        ]
        
        if not kind or kind in cluster_scoped:
            return doc, ""

        if "metadata" not in doc:
            doc["metadata"] = CommentedMap()
            
        metadata = doc["metadata"]
        
        if "namespace" not in metadata:
            # Using CommentedMap logic even for simple strings for consistency
            metadata["namespace"] = "default"
            return doc, "Action: Added 'namespace: default' to satisfy organizational policy."
            
        return doc, ""

    def _rule_inject_resource_limits(self, doc: Any) -> Tuple[Any, str]:
        """
        Policy: Workloads must have CPU/Memory limits to prevent noisy neighbors.
        Refined to preserve CommentedMap structure during injection.
        """
        workload_kinds = ["Deployment", "StatefulSet", "Job", "DaemonSet", "ReplicaSet"]
        
        if doc.get("kind") not in workload_kinds:
            return doc, ""

        modified = False
        try:
            # Traverse the K8s Spec tree safely to the container level
            spec = doc.get("spec", {}).get("template", {}).get("spec", {})
            containers = spec.get("containers", [])
            
            for container in containers:
                if "resources" not in container:
                    # PRO-TIP: We use CommentedMap here so that if the user 
                    # wants to add comments to limits later, the engine supports it.
                    res = CommentedMap()
                    lim = CommentedMap({"cpu": self.default_cpu_limit, "memory": self.default_mem_limit})
                    res["limits"] = lim
                    container["resources"] = res
                    modified = True
                elif "limits" not in container["resources"]:
                    container["resources"]["limits"] = CommentedMap({
                        "cpu": self.default_cpu_limit, 
                        "memory": self.default_mem_limit
                    })
                    modified = True
                    
        except (KeyError, AttributeError):
            # If the structure is too mangled, the Core Engine will catch it; Shield stays silent
            pass

        if modified:
            return doc, f"Warning: Injected default resource limits ({self.default_mem_limit})."
        
        return doc, ""
