"""
유사 이미지 탐지 모듈 - pHash(Perceptual Hash) 기반
리사이즈되거나 재압축된 이미지도 시각적으로 유사하면 탐지합니다.
"""

import os
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import imagehash
    from PIL import Image
    IMAGEHASH_AVAILABLE = True
except ImportError:
    IMAGEHASH_AVAILABLE = False


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
    
    def is_image_file(self, path: str) -> bool:
        """이미지 파일인지 확인"""
        _, ext = os.path.splitext(path)
        return ext.lower() in self.SUPPORTED_EXTENSIONS
    
    def calculate_phash(self, image_path: str) -> Optional[str]:
        """
        이미지의 Perceptual Hash 계산
        
        Args:
            image_path: 이미지 파일 경로
            
        Returns:
            해시 문자열 또는 None (실패 시)
        """
        try:
            with Image.open(image_path) as img:
                # RGBA를 RGB로 변환 (투명도 제거)
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                phash = imagehash.phash(img, hash_size=self.hash_size)
                return str(phash)
        except Exception as e:
            # 손상된 이미지, 지원하지 않는 형식 등
            return None
    
    def calculate_dhash(self, image_path: str) -> Optional[str]:
        """
        Difference Hash 계산 (더 빠름)
        """
        try:
            with Image.open(image_path) as img:
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                dhash = imagehash.dhash(img, hash_size=self.hash_size)
                return str(dhash)
        except Exception:
            return None
    
    def calculate_similarity(self, hash1: str, hash2: str) -> float:
        """
        두 해시 간의 유사도 계산
        
        Args:
            hash1, hash2: 비교할 해시 문자열
            
        Returns:
            유사도 (0.0 ~ 1.0, 1.0이 완전 동일)
        """
        try:
            h1 = imagehash.hex_to_hash(hash1)
            h2 = imagehash.hex_to_hash(hash2)
            # 해밍 거리 계산 (비트 차이 수)
            hamming_distance = h1 - h2
            # 최대 거리는 해시 크기의 제곱
            max_distance = self.hash_size ** 2
            similarity = 1 - (hamming_distance / max_distance)
            return max(0.0, min(1.0, similarity))
        except Exception:
            return 0.0
    
    def find_similar_images(
        self, 
        image_paths: List[str], 
        threshold: float = 0.9,
        progress_callback=None,
        check_cancel=None,
        max_workers: int = 4
    ) -> Dict[str, List[str]]:
        """
        유사 이미지 그룹 찾기
        
        Args:
            image_paths: 이미지 파일 경로 리스트
            threshold: 유사도 임계값 (0.0 ~ 1.0)
            progress_callback: 진행 상황 콜백 함수(current, total)
            check_cancel: 취소 확인 콜백 (True 반환 시 중단)
            max_workers: 병렬 처리 스레드 수
            
        Returns:
            {대표해시: [유사한 이미지 경로들]}
        """
        # Step 1: 모든 이미지의 해시 계산 (병렬)
        path_hashes: Dict[str, str] = {}
        total = len(image_paths)
        
        def calc_hash(path):
            return path, self.calculate_phash(path)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(calc_hash, p): p for p in image_paths}
            completed = 0
            
            for future in as_completed(futures):
                if check_cancel and check_cancel():
                    executor.shutdown(wait=False)
                    return {}
                
                path, hash_val = future.result()
                if hash_val:
                    path_hashes[path] = hash_val
                completed += 1
                if progress_callback:
                    progress_callback(completed, total)
        
        # Step 2: 유사 이미지 그룹핑
        groups: Dict[str, List[str]] = defaultdict(list)
        processed = set()
        
        paths = list(path_hashes.keys())
        hashes = list(path_hashes.values())
        
        for i, path1 in enumerate(paths):
            if path1 in processed:
                continue
            
            hash1 = hashes[i]
            group = [path1]
            processed.add(path1)
            
            for j in range(i + 1, len(paths)):
                path2 = paths[j]
                if path2 in processed:
                    continue
                
                hash2 = hashes[j]
                similarity = self.calculate_similarity(hash1, hash2)
                
                if similarity >= threshold:
                    group.append(path2)
                    processed.add(path2)
            
            # 2개 이상인 그룹만 저장
            if len(group) >= 2:
                groups[hash1] = group
        
        return dict(groups)
    
    def group_similar_images(
        self, 
        hash_results: Dict[str, str],
        threshold: float = 0.9,
        progress_callback=None,
        check_cancel=None
    ) -> List[List[str]]:
        """
        해시 결과를 받아 유사 이미지 그룹 반환
        
        Args:
            hash_results: {이미지경로: 해시값} 딕셔너리
            threshold: 유사도 임계값 (0.0 ~ 1.0)
            progress_callback: 진행 상황 콜백(current, total)
            check_cancel: 취소 확인 콜백
            
        Returns:
            유사 이미지 그룹 리스트 [[path1, path2, ...], ...]
        """
        groups: List[List[str]] = []
        processed = set()
        
        paths = list(hash_results.keys())
        hashes = list(hash_results.values())
        
        for i, path1 in enumerate(paths):
            if path1 in processed:
                continue
            
            if check_cancel and check_cancel():
                return []
            
            hash1 = hashes[i]
            group = [path1]
            processed.add(path1)
            
            for j in range(i + 1, len(paths)):
                if check_cancel and check_cancel():
                    return []
                    
                path2 = paths[j]
                if path2 in processed:
                    continue
                
                hash2 = hashes[j]
                similarity = self.calculate_similarity(hash1, hash2)
                
                if similarity >= threshold:
                    group.append(path2)
                    processed.add(path2)
            
            if progress_callback:
                progress_callback(i + 1, len(paths))
            
            # 2개 이상인 그룹만 저장
            if len(group) >= 2:
                groups.append(group)
        
        return groups
    
    def get_image_info(self, path: str) -> Optional[Dict]:
        """
        이미지 정보 반환 (크기, 모드 등)
        """
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
    """imagehash 라이브러리 사용 가능 여부"""
    return IMAGEHASH_AVAILABLE
