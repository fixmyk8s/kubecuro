import io
import re
import sys
import argparse
from typing import Tuple, Union, List, Dict, Any
from pathlib import Path

# External Dependencies
from ruamel.yaml import YAML, YAMLError
from ruamel.yaml.parser import ParserError
from ruamel.yaml.scanner import ScannerError

from kubecuro.healing.lexer import RawLexer

"""
KUBECURO STRUCTURER - Phase 1.2 (The Architect) - ENTERPRISE GRADE
------------------------------------------------------------------
PURPOSE: Handles ALL indentation disasters (0-∞ spaces) + 8 critical edge cases.
INTEGRATED: Magnetic Snap Alignment (Forces 2-space grid).
"""

class KubeStructurer:
    def __init__(self):
        self.yaml = YAML()
        self.yaml.preserve_quotes = True
        # Standard Kubernetes Indentation
        self.yaml.indent(mapping=2, sequence=4, offset=2)
        self.yaml.width = 4096

    def _normalize_line_endings(self, yaml_str: str) -> str:
        """FIX 1+4: CRLF, LF, CR → Unix LF (all platforms)."""
        return yaml_str.replace('\r\n', '\n').replace('\r', '\n').rstrip()

    def _is_anchor_or_alias(self, line: str) -> bool:
        """FIX 3: Detect &anchor and *alias lines - preserve exactly."""
        content = line.strip()
        return bool(re.match(r'^[ \t]*[&*][a-zA-Z0-9_-]+', content))

    def _is_protected_structure(self, line: str) -> bool:
        """Protect YAML directives, anchors, block scalars from indent changes."""
        content = line.strip()
        return (content.startswith(('%YAML', '%TAG', '---', '...')) or 
                self._is_anchor_or_alias(line) or
                content.startswith(('|', '>')))

    def _extract_line(self, error_info: str) -> int:
        """Parse ruamel.yaml error location from STRUCTURE_ERROR:L5:C3 format."""
        if not error_info.startswith("STRUCTURE_ERROR:L"):
            return -1
        try:
            line_part = error_info.split(':')[1]  # L5
            line_num_1based = int(line_part[1:])
            return line_num_1based - 1
        except (IndexError, ValueError, AttributeError):
            return -1

    def _apply_magnetic_snap(self, yaml_str: str) -> str:
        """
        HIERARCHY EXPANDER: Forces nested lists to be deeper than their parents.
        Specifically fixes the Container -> Env alignment trap.
        """
        lines = yaml_str.splitlines()
        snapped_lines = []
        
        # Track the last 'anchor' indentation for dashes
        last_dash_indent = -1
        
        for line in lines:
            stripped = line.lstrip()
            if not stripped or stripped.startswith('#'):
                snapped_lines.append(line)
                continue
            
            if self._is_protected_structure(line):
                last_dash_indent = -1
                snapped_lines.append(line)
                continue
            
            current_indent = len(line) - len(stripped)
            # Standard grid snap
            snapped_indent = round(current_indent / 2) * 2

            if stripped.startswith('- '):
                # If we've seen a dash before, and this new dash is at the 
                # same or similar level but was ORIGINALLY deeper, 
                # force it to be at least 2 spaces deeper than the parent dash.
                if last_dash_indent != -1:
                    if current_indent > last_dash_indent and snapped_indent <= last_dash_indent:
                        snapped_indent = last_dash_indent + 2
                
                last_dash_indent = snapped_indent
            else:
                # Reset if we move back out to a parent key
                if snapped_indent < last_dash_indent:
                    last_dash_indent = -1

            snapped_lines.append(" " * snapped_indent + stripped)
        
        return "\n".join(snapped_lines)

    def _find_parent_indent(self, lines: List[str], err_line: int) -> int:
        """
        FIX 5: Skip empty lines + comments + protected structures.
        Finds closest mapping key above error line.
        """
        for i in range(err_line - 1, -1, -1):
            if i < 0: break
            
            raw_content = re.split(r'\s+#', lines[i])[0].rstrip()
            
            if (not raw_content.strip() or 
                raw_content.strip().startswith('#') or 
                self._is_protected_structure(raw_content)):
                continue
                
            content = raw_content.lstrip()
            if raw_content.endswith(':') and not content.startswith('- '):
                return len(raw_content) - len(content)
        return 0

    def _process_single_doc(self, yaml_str: str) -> Tuple[str, str]:
        """Process single YAML document with iterative fixing."""
        # NEW: First pass - Magnetic Snap (Brute force alignment)
        snapped_yaml = self._apply_magnetic_snap(yaml_str)

        # Step 1: Initial validation
        valid, result = self.validate_and_roundtrip(snapped_yaml)
        if valid:
            return result, "STRUCTURE_OK"

        # FIX 6: Iterative multi-error fixing (max 3 attempts)
        current_yaml = snapped_yaml
        for attempt in range(3):
            fixed_yaml = self.auto_fix_indentation(current_yaml, result)
            
            # Check if we are stuck on a protected structure
            err_idx = self._extract_line(result)
            if err_idx != -1 and err_idx < len(fixed_yaml.splitlines()):
                if self._is_protected_structure(fixed_yaml.splitlines()[err_idx]):
                    return current_yaml, "STRUCTURE_PROTECTED_SKIP"
            
            valid2, result2 = self.validate_and_roundtrip(fixed_yaml)
            if valid2:
                return result2, f"STRUCTURE_FIXED_{attempt+1}"
            
            current_yaml = fixed_yaml
            result = result2 
        
        return current_yaml, "STRUCTURE_FAIL"

    def _process_multi_doc(self, yaml_str: str) -> str:
        """FIX 2: Process each --- document separately."""
        documents = re.split(r'\n(?=---)', yaml_str.strip())
        fixed_docs = []
        
        for doc in documents:
            if doc.strip():
                fixed_doc, status = self._process_single_doc(doc)
                fixed_docs.append(fixed_doc)
        
        return '\n---\n'.join(fixed_docs)

    def auto_fix_indentation(self, yaml_str: str, error_info: str) -> str:
        """Heals specific line-based errors reported by the parser."""
        err_line = self._extract_line(error_info)
        if err_line == -1: return yaml_str

        lines = yaml_str.splitlines()
        if err_line >= len(lines): return yaml_str

        target_line = lines[err_line].replace('\t', '  ')
        if self._is_protected_structure(target_line): return yaml_str

        current_indent = len(target_line) - len(target_line.lstrip())
        parent_indent = self._find_parent_indent(lines, err_line)
        
        # KUBERNETES HIERARCHY RULE
        target_indent = parent_indent + 2

        if (current_indent != target_indent or '\t' in target_line or current_indent % 2 != 0):
            fixed_line = (' ' * target_indent + target_line.lstrip()).rstrip()
            lines[err_line] = fixed_line
            return '\n'.join(lines)
        
        return yaml_str

    def validate_and_roundtrip(self, clean_yaml: str) -> Tuple[bool, str]:
        """Structural validation via ruamel.yaml roundtrip."""
        try:
            data = self.yaml.load(clean_yaml)
            output_buffer = io.StringIO()
            self.yaml.dump(data, output_buffer)
            return True, output_buffer.getvalue().rstrip()
        except YAMLError as e:
            mark = getattr(e, 'problem_mark', getattr(e, 'context_mark', None))
            if mark:
                line_num = mark.line + 1
                col_num = mark.column + 1
                return False, f"STRUCTURE_ERROR:L{line_num}:C{col_num}:{str(e)}"
            return False, f"STRUCTURE_ERROR:{str(e)}"

    def process_yaml(self, lexer_output: str) -> Tuple[str, str]:
        """Phase 1.2 Entry Point."""
        normalized = self._normalize_line_endings(lexer_output)
        
        if '---' in normalized:
            result = self._process_multi_doc(normalized)
            return result, "MULTI_DOC_HANDLED"
        
        return self._process_single_doc(normalized)

    def full_healing_report(self, original: str, final: str, status: str) -> Dict[str, Any]:
        """Production-grade healing summary."""
        original_lines = original.splitlines()
        final_lines = final.splitlines()
        changes = []
        
        # Only compare up to the shortest file length to avoid zip issues
        for i, (orig, fixed) in enumerate(zip(original_lines, final_lines)):
            if orig != fixed:
                changes.append({
                    'line': i + 1,
                    'original': orig,
                    'fixed': fixed,
                    'indent_original': len(orig) - len(orig.lstrip()),
                    'indent_fixed': len(fixed) - len(fixed.lstrip())
                })
        
        return {
            'status': status,
            'total_lines': len(original_lines),
            'lines_changed': len(changes),
            'changes': changes
        }
