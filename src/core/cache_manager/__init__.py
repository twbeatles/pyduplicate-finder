from .database import CacheDatabaseMixin
from .exemptions import CacheExemptionMixin
from .hash_cache import CacheHashMixin
from .jobs import CacheJobMixin
from .operations import CacheOperationMixin
from .quarantine import CacheQuarantineMixin
from .reviews import CacheReviewMixin
from .scan_storage import CacheScanStorageMixin
from .schema import CacheSchemaMixin
from .sessions import CacheSessionMixin
from .signatures import CacheSignatureMixin


class CacheManager(
    CacheJobMixin,
    CacheExemptionMixin,
    CacheHashMixin,
    CacheQuarantineMixin,
    CacheOperationMixin,
    CacheReviewMixin,
    CacheScanStorageMixin,
    CacheSessionMixin,
    CacheSignatureMixin,
    CacheSchemaMixin,
    CacheDatabaseMixin,
):
    SCHEMA_VERSION = 6


__all__ = ["CacheManager"]
