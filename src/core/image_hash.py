"""
유사 이미지 탐지 모듈 - pHash(Perceptual Hash) 기반
리사이즈되거나 재압축된 이미지도 시각적으로 유사하면 탐지합니다.
"""

import os
from collections import defaultdict
from typing import Dict, List, Tuple, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import imagehash
    from PIL import Image
    IMAGEHASH_AVAILABLE = True
except ImportError:
    IMAGEHASH_AVAILABLE = False


class BKTree:
    """
    Burkhard-Keller Tree for fast metric space searching (Hamming distance).
    """
    def __init__(self, distance_func):
        self._root = None
        self._distance_func = distance_func

    def add(self, item):
        if self._root is None:
            self._root = (item, {})
            return

        node = self._root
        while True:
            parent_item, children = node
            dist = self._distance_func(item, parent_item)
            if dist == 0: # Identical logic (duplicate hash), no need to add new node structure, just skip
                 break
            
            if dist in children:
                node = children[dist]
            else:
                children[dist] = (item, {})
                break

    def search(self, item, radius):
        """Find all items within radius distance."""
        if self._root is None:
            return []

        candidates = [self._root]
        found = []

        while candidates:
            node = candidates.pop()
            parent_item, children = node
            dist = self._distance_func(item, parent_item)

            if dist <= radius:
                found.append(parent_item)

            start = dist - radius
            end = dist + radius

            for d, child in children.items():
                if start <= d <= end:
                    candidates.append(child)
        
        return found


class UnionFind:
    """Simple Union-Find (Disjoint Set) data structure."""
    def __init__(self, elements):
        self.parent = {e: e for e in elements}

    def find(self, item):
        if self.parent[item] == item:
            return item
        self.parent[item] = self.find(self.parent[item])  # Path compression
        return self.parent[item]

    def union(self, a, b):
        root_a = self.find(a)
        root_b = self.find(b)
        if root_a != root_b:
            self.parent[root_b] = root_a


class ImageHasher:
    """pHash를 사용한 유사 이미지 탐지 클래스"""
    
    SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tiff', '.tif'}
    
    def __init__(self, hash_size: int = 16):
        """
        Args:
            hash_size: 해시 크기 (기본값 16, 클수록 정밀하지만 느림)
        """
        if not IMAGEHASH_AVAILABLE:
            raise ImportError("imagehash 및 Pillow 라이브러리가 필요합니다. pip install imagehash Pillow")
        self.hash_size = hash_size
        self.max_distance = hash_size ** 2
    
    def is_image_file(self, path: str) -> bool:
        """이미지 파일인지 확인"""
        _, ext = os.path.splitext(path)
        return ext.lower() in self.SUPPORTED_EXTENSIONS
    
    def calculate_phash(self, image_path: str) -> Optional[str]:
        """이미지의 Perceptual Hash 계산"""
        try:
            with Image.open(image_path) as img:
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                phash = imagehash.phash(img, hash_size=self.hash_size)
                return str(phash)
        except Exception:
            return None
    
    def calculate_distance(self, hash1_str: str, hash2_str: str) -> int:
        """두 해시 문자열 간의 해밍 거리 계산"""
        try:
            h1 = imagehash.hex_to_hash(hash1_str)
            h2 = imagehash.hex_to_hash(hash2_str)
            return h1 - h2
        except:
            return self.max_distance

    def calculate_similarity(self, hash1: str, hash2: str) -> float:
        """두 해시 간의 유사도 계산 (0.0 ~ 1.0)"""
        dist = self.calculate_distance(hash1, hash2)
        return max(0.0, 1.0 - (dist / self.max_distance))
    
    def group_similar_images(
        self, 
        hash_results: Dict[str, str],
        threshold: float = 0.9,
        progress_callback=None,
        check_cancel=None
    ) -> List[List[str]]:
        """
        BK-Tree와 Union-Find를 사용하여 효율적으로 유사 이미지를 그룹핑합니다.
        Complexity: ~O(N log N)
        """
        if not hash_results:
            return []

        # 1. Prepare Data
        # Map hash -> list of paths (to handle exact duplicates efficiently)
        hash_to_paths = defaultdict(list)
        for path, h in hash_results.items():
            hash_to_paths[h].append(path)
        
        unique_hashes = list(hash_to_paths.keys())
        total_hashes = len(unique_hashes)
        
        # 2. Build BK-Tree
        bktree = BKTree(self.calculate_distance)
        for h in unique_hashes:
            bktree.add(h)
            if check_cancel and check_cancel(): return []

        # 3. Find Connected Components using Union-Find
        uf = UnionFind(unique_hashes)
        
        # Calculate max allowed distance for threshold
        # similarity = 1 - (dist / max_dist)
        # dist = (1 - similarity) * max_dist
        allowed_dist = int((1.0 - threshold) * self.max_distance)
        
        processed_count = 0
        
        # Search for neighbors
        for h in unique_hashes:
            if check_cancel and check_cancel(): return []
            
            # Find neighbors within distance
            neighbors = bktree.search(h, allowed_dist)
            
            for n in neighbors:
                if h != n:
                    uf.union(h, n)
            
            processed_count += 1
            if progress_callback and processed_count % 10 == 0:
                progress_callback(processed_count, total_hashes)

        # 4. Collect Groups
        # Group hashes by their root parent in Union-Find
        groups_by_root = defaultdict(list)
        for h in unique_hashes:
            root = uf.find(h)
            groups_by_root[root].append(h)
        
        # 5. Convert back to paths
        final_groups = []
        for root, hashes in groups_by_root.items():
            # Gather all paths for all hashes in this group
            file_paths = []
            for h in hashes:
                file_paths.extend(hash_to_paths[h])
            
            if len(file_paths) >= 2:
                final_groups.append(file_paths)
                
        return final_groups
    
    def get_image_info(self, path: str) -> Optional[Dict]:
        try:
            with Image.open(path) as img:
                return {
                    'width': img.width,
                    'height': img.height,
                    'mode': img.mode,
                    'format': img.format
                }
        except Exception:
            return None


def is_available() -> bool:
    return IMAGEHASH_AVAILABLE
