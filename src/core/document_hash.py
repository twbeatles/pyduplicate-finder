from __future__ import annotations

import hashlib
import io
import os
import re
from collections import defaultdict

try:
    from pypdf import PdfReader

    PDF_AVAILABLE = True
except Exception:
    PdfReader = None
    PDF_AVAILABLE = False


class SimHashBKTree:
    def __init__(self):
        self._root = None

    @staticmethod
    def distance(a: int, b: int) -> int:
        return (int(a) ^ int(b)).bit_count()

    def add(self, item: int) -> None:
        if self._root is None:
            self._root = (item, {})
            return
        node = self._root
        while True:
            value, children = node
            dist = self.distance(item, value)
            if dist == 0:
                break
            if dist in children:
                node = children[dist]
            else:
                children[dist] = (item, {})
                break

    def search(self, item: int, radius: int) -> list[int]:
        if self._root is None:
            return []
        found: list[int] = []
        queue = [self._root]
        while queue:
            value, children = queue.pop()
            dist = self.distance(item, value)
            if dist <= radius:
                found.append(value)
            start = dist - radius
            end = dist + radius
            for child_dist, child in children.items():
                if start <= child_dist <= end:
                    queue.append(child)
        return found


class SimHashUnionFind:
    def __init__(self, elements):
        self.parent = {e: e for e in elements}

    def find(self, item):
        if self.parent[item] == item:
            return item
        self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, a, b):
        ra = self.find(a)
        rb = self.find(b)
        if ra != rb:
            self.parent[rb] = ra


class DocumentHasher:
    SUPPORTED_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".py", ".pdf"}

    @staticmethod
    def is_supported(path: str) -> bool:
        return os.path.splitext(str(path or ""))[1].lower() in DocumentHasher.SUPPORTED_EXTENSIONS

    @staticmethod
    def _normalize_text(text: str) -> str:
        lowered = str(text or "").lower()
        lowered = re.sub(r"\s+", " ", lowered)
        lowered = re.sub(r"[^\w\s]", " ", lowered)
        lowered = re.sub(r"\s+", " ", lowered)
        return lowered.strip()

    def extract_text(self, path: str) -> str | None:
        ext = os.path.splitext(str(path or ""))[1].lower()
        try:
            if ext == ".pdf":
                if not PDF_AVAILABLE or PdfReader is None:
                    return None
                with open(path, "rb") as fh:
                    reader = PdfReader(fh)
                    parts: list[str] = []
                    for page in reader.pages:
                        parts.append(page.extract_text() or "")
                    return self._normalize_text("\n".join(parts))

            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                return self._normalize_text(fh.read())
        except Exception:
            return None

    def calculate_simhash(self, path: str) -> str | None:
        text = self.extract_text(path)
        if not text:
            return None
        weights = [0] * 64
        tokens = re.findall(r"\w+", text)
        if not tokens:
            return None
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8", errors="ignore"), digest_size=8).digest()
            value = int.from_bytes(digest, "big", signed=False)
            for idx in range(64):
                if value & (1 << idx):
                    weights[idx] += 1
                else:
                    weights[idx] -= 1
        out = 0
        for idx, weight in enumerate(weights):
            if weight > 0:
                out |= 1 << idx
        return f"{out:016x}"

    def calculate_similarity(self, hash1: str, hash2: str) -> float:
        try:
            left = int(str(hash1), 16)
            right = int(str(hash2), 16)
        except Exception:
            return 0.0
        distance = (left ^ right).bit_count()
        return max(0.0, 1.0 - (distance / 64.0))

    def group_similar_documents(self, hash_results: dict[str, str], threshold: float = 0.9, progress_callback=None, check_cancel=None):
        if not hash_results:
            return []
        hash_to_paths = defaultdict(list)
        for path, value in hash_results.items():
            hash_to_paths[value].append(path)
        unique_hashes = [int(h, 16) for h in hash_to_paths.keys()]
        tree = SimHashBKTree()
        for item in unique_hashes:
            tree.add(item)
            if check_cancel and check_cancel():
                return []
        uf = SimHashUnionFind(unique_hashes)
        radius = max(0, int((1.0 - float(threshold or 0.9)) * 64.0))
        total = len(unique_hashes)
        processed = 0
        for item in unique_hashes:
            if check_cancel and check_cancel():
                return []
            for neighbor in tree.search(item, radius):
                if neighbor != item:
                    uf.union(item, neighbor)
            processed += 1
            if progress_callback and processed % 10 == 0:
                progress_callback(processed, total)
        groups = defaultdict(list)
        for item in unique_hashes:
            groups[uf.find(item)].append(item)
        out = []
        for items in groups.values():
            paths: list[str] = []
            for item in items:
                paths.extend(hash_to_paths.get(f"{item:016x}", []))
            if len(paths) >= 2:
                out.append(paths)
        return out


def is_available() -> bool:
    return PDF_AVAILABLE
