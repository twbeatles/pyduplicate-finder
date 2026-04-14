from __future__ import annotations

import concurrent.futures
import errno
import fnmatch
import hashlib
import logging
import os
import platform
import threading
import time
from collections import defaultdict
from typing import Any

from PySide6.QtCore import QMutex, QMutexLocker, QThread, Signal

from src.core.cache_manager import CacheManager
from src.utils.i18n import strings

DEBUG_SCAN = os.environ.get("PYDUPLICATEFINDER_DEBUG_SCAN", "").lower() in ("1", "true", "yes")
logger = logging.getLogger(__name__)

_ImageHasher = None
try:
    from src.core.image_hash import ImageHasher as _ImageHasher, is_available as _image_hash_available
except ImportError:
    _ImageHasher = None

    def _image_hash_available() -> bool:
        return False


IMAGE_HASH_AVAILABLE = bool(_image_hash_available())
_DocumentHasher = None
try:
    from src.core.document_hash import DocumentHasher as _DocumentHasher, is_available as _document_hash_available
except ImportError:
    _DocumentHasher = None

    def _document_hash_available() -> bool:
        return False


DOCUMENT_HASH_AVAILABLE = bool(_document_hash_available())
BUFFER_SIZE = 1024 * 1024
