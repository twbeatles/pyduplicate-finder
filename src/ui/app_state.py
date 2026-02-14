from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class AppState:
    """
    Shared UI state snapshot.

    Note: The existing app stores many values directly on the main window.
    This dataclass provides a consistent place to consolidate state over time.
    """

    selected_folders: List[str] = field(default_factory=list)
    scan_config: Dict = field(default_factory=dict)
    scan_results: Dict = field(default_factory=dict)
    current_session_id: Optional[int] = None

    is_scanning: bool = False

    selection_rules: List[Dict] = field(default_factory=list)
    exclude_patterns: List[str] = field(default_factory=list)
    custom_shortcuts: Dict[str, str] = field(default_factory=dict)

    theme: str = "light"
    language: str = "ko"

