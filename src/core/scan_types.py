from __future__ import annotations

from dataclasses import dataclass, field


SELECTION_POLICY_SMART = "smart"
SELECTION_POLICY_OLDEST = "oldest"
SELECTION_POLICY_NEWEST = "newest"
SELECTION_POLICY_PATH_SHORTEST = "path_shortest"
SELECTION_POLICY_EXTENSION_PRIORITY = "extension_priority"
SELECTION_POLICY_PRIMARY_KEEP = "primary_keep"

EXEMPTION_KIND_EXACT_PATH = "exact_path"
EXEMPTION_KIND_PATH_GLOB = "path_glob"
EXEMPTION_KIND_CONTENT_HASH = "content_hash"

EXEMPTION_ACTION_SAFELIST = "safelist"
EXEMPTION_ACTION_IGNORE = "ignore"

EXEMPTION_STATUS_SAFELISTED = "safelisted"
EXEMPTION_STATUS_IGNORE = "ignore"

REVIEW_STATE_UNREVIEWED = "unreviewed"
REVIEW_STATE_KEEP = "reviewed_keep"
REVIEW_STATE_DELETE_LATER = "reviewed_delete_later"

COLLECTION_ROLE_PRIMARY = "primary"
COLLECTION_ROLE_SECONDARY = "secondary"
COLLECTION_ROLE_NONE = ""

COMPARE_MODE_NONE = "none"
COMPARE_MODE_COLLECTIONS = "collections"


def normalize_exemption_status(value: object) -> str:
    token = str(value or "").strip().lower()
    if token in {EXEMPTION_STATUS_SAFELISTED, EXEMPTION_ACTION_SAFELIST}:
        return EXEMPTION_STATUS_SAFELISTED
    if token == EXEMPTION_STATUS_IGNORE:
        return EXEMPTION_STATUS_IGNORE
    return ""


@dataclass(frozen=True)
class SelectionPolicy:
    mode: str = SELECTION_POLICY_SMART
    preferred_extensions: tuple[str, ...] = ()
    prefer_shorter_path: bool = True
    prefer_readonly: bool = True
    collection_preference: str = COLLECTION_ROLE_PRIMARY


@dataclass(frozen=True)
class ExemptionRule:
    kind: str
    value: str
    action: str
    note: str = ""


@dataclass(frozen=True)
class ReviewMark:
    session_id: int
    target_type: str
    target_key: str
    state: str


@dataclass(frozen=True)
class SelectionCandidate:
    path: str
    mtime: float = 0.0
    extension: str = ""
    collection_role: str = COLLECTION_ROLE_NONE
    explicit_keep: bool = False
    explicit_delete: bool = False
    safelisted: bool = False
    readonly: bool = False


@dataclass
class SelectionDecision:
    keep_set: set[str] = field(default_factory=set)
    delete_set: set[str] = field(default_factory=set)
    reasons: dict[str, str] = field(default_factory=dict)
