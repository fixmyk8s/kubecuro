from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class ShadowMetadata:
    above_comments: List[str] = field(default_factory=list)
    inline_comment: Optional[str] = None

class KubeShadow:
    """
    The Curator: Records comments and formatting 'metadata' 
    to preserve developer intent during reconstruction.
    """
    def __init__(self):
        self.comment_map: Dict[int, ShadowMetadata] = {}
        self.orphans: List[str] = []

    def capture(self, raw_text: str):
        lines = raw_text.splitlines()
        pending_comments = []

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # 1. Capture Full-Line Comments
            if stripped.startswith('#'):
                pending_comments.append(line)
                continue

            # 2. Skip Blanks
            if not stripped:
                continue

            # 3. Associate with Data Line
            inline_part = None
            if '#' in line:
                _, inline_part = line.split('#', 1)
                inline_part = f"#{inline_part}"

            if pending_comments or inline_part:
                self.comment_map[i] = ShadowMetadata(
                    above_comments=pending_comments.copy(),
                    inline_comment=inline_part
                )
                pending_comments.clear()

        self.orphans = pending_comments

    def get_metadata(self, line_no: int) -> Optional[ShadowMetadata]:
        return self.comment_map.get(line_no)
