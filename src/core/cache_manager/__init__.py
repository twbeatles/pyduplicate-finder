from .database import CacheDatabaseMixin
from .hash_cache import CacheHashMixin
from .jobs import CacheJobMixin
from .operations import CacheOperationMixin
from .quarantine import CacheQuarantineMixin
from .scan_storage import CacheScanStorageMixin
from .schema import CacheSchemaMixin
from .sessions import CacheSessionMixin


class CacheManager(
    CacheJobMixin,
    CacheHashMixin,
    CacheQuarantineMixin,
    CacheOperationMixin,
    CacheScanStorageMixin,
    CacheSessionMixin,
    CacheSchemaMixin,
    CacheDatabaseMixin,
):
    SCHEMA_VERSION = 5


__all__ = ["CacheManager"]
