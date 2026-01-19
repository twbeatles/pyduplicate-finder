"""
스캔 프리셋 관리자
스캔 설정을 프리셋으로 저장/로드하는 기능을 제공합니다.
"""

import json
import os
from typing import Dict, List, Optional, Any
from datetime import datetime


class PresetManager:
    """스캔 프리셋 관리 클래스"""
    
    DEFAULT_PRESET_DIR = os.path.join(os.path.expanduser("~"), ".pyduplicatefinder", "presets")
    
    def __init__(self, preset_dir: Optional[str] = None):
        """
        Args:
            preset_dir: 프리셋 저장 디렉토리 (기본값: ~/.pyduplicatefinder/presets)
        """
        self.preset_dir = preset_dir or self.DEFAULT_PRESET_DIR
        os.makedirs(self.preset_dir, exist_ok=True)
    
    def _get_preset_path(self, name: str) -> str:
        """프리셋 파일 경로 반환"""
        # 파일명에 사용할 수 없는 문자 제거
        safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
        return os.path.join(self.preset_dir, f"{safe_name}.json")
    
    def save_preset(self, name: str, config: Dict[str, Any]) -> bool:
        """
        프리셋 저장
        
        Args:
            name: 프리셋 이름
            config: 설정 딕셔너리
            
        Returns:
            성공 여부
        """
        try:
            preset_data = {
                'name': name,
                'created_at': datetime.now().isoformat(),
                'config': config
            }
            
            path = self._get_preset_path(name)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(preset_data, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            print(f"Error saving preset: {e}")
            return False
    
    def load_preset(self, name: str) -> Optional[Dict[str, Any]]:
        """
        프리셋 로드
        
        Args:
            name: 프리셋 이름
            
        Returns:
            설정 딕셔너리 또는 None
        """
        try:
            path = self._get_preset_path(name)
            if not os.path.exists(path):
                return None
            
            with open(path, 'r', encoding='utf-8') as f:
                preset_data = json.load(f)
            
            return preset_data.get('config', {})
        except Exception as e:
            print(f"Error loading preset: {e}")
            return None
    
    def delete_preset(self, name: str) -> bool:
        """
        프리셋 삭제
        
        Args:
            name: 프리셋 이름
            
        Returns:
            성공 여부
        """
        try:
            path = self._get_preset_path(name)
            if os.path.exists(path):
                os.remove(path)
                return True
            return False
        except Exception as e:
            print(f"Error deleting preset: {e}")
            return False
    
    def list_presets(self) -> List[Dict[str, Any]]:
        """
        모든 프리셋 목록 반환
        
        Returns:
            [{'name': ..., 'created_at': ..., 'path': ...}, ...]
        """
        presets = []
        try:
            for filename in os.listdir(self.preset_dir):
                if filename.endswith('.json'):
                    path = os.path.join(self.preset_dir, filename)
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            presets.append({
                                'name': data.get('name', filename[:-5]),
                                'created_at': data.get('created_at', ''),
                                'path': path
                            })
                    except:
                        continue
        except Exception:
            pass
        
        # 생성일 기준 정렬
        presets.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return presets
    
    def get_preset_names(self) -> List[str]:
        """프리셋 이름 목록만 반환"""
        return [p['name'] for p in self.list_presets()]
    
    def export_preset(self, name: str, export_path: str) -> bool:
        """
        프리셋을 외부 파일로 내보내기
        
        Args:
            name: 프리셋 이름
            export_path: 내보낼 파일 경로
            
        Returns:
            성공 여부
        """
        try:
            src_path = self._get_preset_path(name)
            if not os.path.exists(src_path):
                return False
            
            import shutil
            shutil.copy(src_path, export_path)
            return True
        except Exception as e:
            print(f"Error exporting preset: {e}")
            return False
    
    def import_preset(self, import_path: str) -> Optional[str]:
        """
        외부 파일에서 프리셋 가져오기
        
        Args:
            import_path: 가져올 파일 경로
            
        Returns:
            가져온 프리셋 이름 또는 None
        """
        try:
            with open(import_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            name = data.get('name', os.path.basename(import_path)[:-5])
            config = data.get('config', {})
            
            if self.save_preset(name, config):
                return name
            return None
        except Exception as e:
            print(f"Error importing preset: {e}")
            return None
    
    def preset_exists(self, name: str) -> bool:
        """프리셋 존재 여부 확인"""
        return os.path.exists(self._get_preset_path(name))


def get_default_config() -> Dict[str, Any]:
    """기본 스캔 설정 반환"""
    return {
        'folders': [],
        'extensions': '',
        'min_size_kb': 0,
        'protect_system': True,
        'byte_compare': False,
        'same_name': False,
        'name_only': False,
        'exclude_patterns': [],
        'use_similar_image': False,
        'similarity_threshold': 0.9,
        'use_trash': False
    }
