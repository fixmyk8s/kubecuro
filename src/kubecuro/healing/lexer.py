import re

class KubeLexer:
    """
    KUBECURO LEXER - The Refurbisher (Phase 1.1)
    --------------------------------------------
    Incorporates 15 structural fixes including block protection,
    stuck colon/dash repair, and quote-aware comment splitting.
    """
    def __init__(self):
        self.in_block = False
        self.block_indent = 0

    def _find_comment_split(self, text: str) -> int:
        """Protects quotes and # symbols inside values."""
        in_double_quote = False
        in_single_quote = False
        escaped = False
        for i, char in enumerate(text):
            if escaped:
                escaped = False
                continue
            if char == '\\':
                escaped = True
                continue
            if char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
            elif char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
            if char == '#' and not in_double_quote and not in_single_quote:
                if i == 0 or text[i-1].isspace():
                    return i
        return -1

    def repair_line(self, line: str) -> str:
        # 1. Tabs & Basic Cleaning (Case 1 & 4)
        raw_line = line.replace('\t', '  ').rstrip()
        content = raw_line.lstrip()
        if not content: return raw_line
        
        indent = len(raw_line) - len(content)

        # 2. Block Protection (Case 12 & 13)
        if self.in_block:
            if indent <= self.block_indent and (':' in content or content.startswith('-')):
                self.in_block = False
            else:
                return raw_line

        # 3. Comment Separation (Case 8, 9, 10)
        split_idx = self._find_comment_split(raw_line)
        if split_idx != -1:
            code_part = raw_line[:split_idx]
            comment_part = raw_line[split_idx:]
        else:
            code_part = raw_line
            comment_part = ""

        # 4. SURGICAL FIXES (Case 2 & 3)
        # Fix Stuck Dash: '-image' -> '- image'
        if code_part.lstrip().startswith('-') and len(code_part.lstrip()) > 1:
            if code_part.lstrip()[1].isalpha():
                code_part = code_part.replace('-', '- ', 1)

        # Fix Stuck Colon: 'kind:Pod' -> 'kind: Pod' (Case 2, 7)
        # PROTECT IMAGE TAGS: nginx:1.14
        if not re.search(r'image[:\s]*[a-zA-Z0-9/]', code_part):
            code_part = re.sub(r'(?<!http)(?<!https):(?!\s)([a-zA-Z])', r': \1', code_part)

        # 5. State Management
        if any(marker in code_part for marker in ['|', '>', '|-', '>-']):
            self.in_block = True
            self.block_indent = indent

        return code_part + comment_part

    def repair(self, raw_yaml: str) -> str:
        """
        The entry point used by HealingPipeline.
        Orchestrates line-by-line repair while handling block states.
        """
        self.in_block = False
        lines = raw_yaml.splitlines()
        fixed = []
        for i, line in enumerate(lines):
            # Recovery for flush-left list items
            if i > 0 and lines[i-1].rstrip().endswith(':') and line.startswith('-'):
                p_indent = len(lines[i-1]) - len(lines[i-1].lstrip())
                line = (' ' * (p_indent + 2)) + line
            fixed.append(self.repair_line(line))
        return "\n".join(fixed)
