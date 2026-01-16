import re
from typing import List, Tuple, Optional
from kubecuro.core.models import Shard

class KubeScanner:
    """
    The Archeologist: Mines identity and structural 'shards' from 
    potentially non-compliant YAML text.
    """
    
    # Regex to catch key: value even if spaces are missing or weird
    # Group 1: Leading spaces (indent)
    # Group 2: Optional list dash
    # Group 3: Key
    # Group 4: Value (optional)
    LINE_PATTERN = re.compile(r'^(\s*)(?:(-\s*))?([\w\.\-\/]+)\s*:\s*(.*)$')
    
    def __init__(self):
        self.found_kind: Optional[str] = None
        self.found_api: Optional[str] = None

    def scan(self, raw_text: str) -> List[Shard]:
        shards = []
        lines = raw_text.splitlines()
        
        for i, line in enumerate(lines, 1):
            # Skip empty lines or full-line comments (handled by shadow.py later)
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue

            match = self.LINE_PATTERN.match(line)
            if match:
                indent_str, list_prefix, key, value = match.groups()
                indent_len = len(indent_str)
                is_list = list_prefix is not None
                
                # Cleanup value
                clean_value = value.strip() if value else None
                
                # Track Identity (Identity Probe)
                if key == "kind" and clean_value:
                    self.found_kind = clean_value
                if key == "apiVersion" and clean_value:
                    self.found_api = clean_value

                shard = Shard(
                    line_no=i,
                    indent=indent_len,
                    key=key,
                    value=clean_value,
                    is_list_start=is_list,
                    raw_line=line
                )
                shards.append(shard)
            else:
                # This is a 'Dangling Value' or part of a block scalar
                # In a real-world scenario, we'd handle multi-line strings here
                pass
                
        return shards

    def get_identity(self) -> Tuple[Optional[str], Optional[str]]:
        """Returns (kind, apiVersion) found during scan."""
        return self.found_kind, self.found_api
