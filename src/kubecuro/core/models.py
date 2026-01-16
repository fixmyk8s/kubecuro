from dataclasses import dataclass
from typing import Optional, Any

@dataclass
class Shard:
    line_no: int
    indent: int
    key: str
    value: Optional[str] = None
    is_list_start: bool = False
    raw_line: str = ""
