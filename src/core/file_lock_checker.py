"""
파일 잠금 감지 모듈
삭제 전 파일이 다른 프로세스에 의해 사용 중인지 확인합니다.
"""

import os
import platform
from typing import List, Tuple, Optional


class FileLockChecker:
    """파일 잠금 상태 확인 클래스"""
    
    def __init__(self):
        self.is_windows = platform.system() == 'Windows'
    
    def is_file_locked(self, path: str) -> bool:
        """
        파일이 다른 프로세스에 의해 잠겨있는지 확인
        
        Args:
            path: 파일 경로
            
        Returns:
            True = 잠겨있음, False = 사용 가능
        """
        if not os.path.exists(path):
            return False
        
        if os.path.isdir(path):
            return False
        
        # 크기 0 파일은 잠금 체크 불필요 (msvcrt.locking 오류 방지)
        try:
            if os.path.getsize(path) == 0:
                return False
        except OSError:
            return True
        
        try:
            # 쓰기 모드로 파일 열기 시도
            # 잠겨있으면 PermissionError 또는 OSError 발생
            if self.is_windows:
                # Windows: 배타적 접근 시도
                import msvcrt
                with open(path, 'r+b') as f:
                    try:
                        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                        return False
                    except (IOError, OSError):
                        return True
            else:
                # Linux/Mac: fcntl 사용
                import fcntl
                with open(path, 'r+b') as f:
                    try:
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                        return False
                    except (IOError, OSError):
                        return True
        except PermissionError:
            # 권한 부족 = 잠겨있거나 접근 불가
            return True
        except FileNotFoundError:
            return False
        except Exception:
            # 기타 예외는 잠금으로 간주
            return True
    
    def check_files(self, paths: List[str]) -> List[Tuple[str, bool]]:
        """
        여러 파일의 잠금 상태 일괄 확인
        
        Args:
            paths: 파일 경로 리스트
            
        Returns:
            [(경로, 잠김여부), ...] 리스트
        """
        results = []
        for path in paths:
            locked = self.is_file_locked(path)
            results.append((path, locked))
        return results
    
    def get_locked_files(self, paths: List[str]) -> List[str]:
        """
        잠긴 파일만 필터링하여 반환
        
        Args:
            paths: 파일 경로 리스트
            
        Returns:
            잠긴 파일 경로 리스트
        """
        return [path for path, locked in self.check_files(paths) if locked]
    
    def get_unlocked_files(self, paths: List[str]) -> List[str]:
        """
        잠기지 않은 파일만 필터링하여 반환
        
        Args:
            paths: 파일 경로 리스트
            
        Returns:
            사용 가능한 파일 경로 리스트
        """
        return [path for path, locked in self.check_files(paths) if not locked]
    
    def get_locking_processes(self, path: str, max_results: int = 5, timeout_seconds: float = 2.0) -> List[str]:
        """
        파일을 잠그고 있는 프로세스 목록 반환 (Windows 전용)
        
        Issue #5: 성능 개선 - 조기 종료, 타임아웃 처리
        
        Args:
            path: 파일 경로
            max_results: 최대 결과 수 (기본값 5, 조기 종료)
            timeout_seconds: 타임아웃 시간 (기본값 2초)
            
        Returns:
            프로세스 이름 리스트 (지원하지 않는 OS에서는 빈 리스트)
        """
        if not self.is_windows:
            return []
        
        try:
            import psutil
            import time
            
            abs_path = os.path.abspath(path).lower()
            locking_procs = []
            start_time = time.time()
            
            for proc in psutil.process_iter(['pid', 'name']):
                # Issue #5: 타임아웃 체크
                if time.time() - start_time > timeout_seconds:
                    break
                    
                # Issue #5: 조기 종료 (max_results 도달 시)
                if len(locking_procs) >= max_results:
                    break
                
                try:
                    # 프로세스가 열고 있는 파일 확인
                    for f in proc.open_files():
                        if f.path.lower() == abs_path:
                            locking_procs.append(f"{proc.info['name']} (PID: {proc.info['pid']})")
                            break
                except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                    continue
            
            return locking_procs
        except ImportError:
            # psutil 미설치
            return []
        except Exception:
            return []


def check_single_file(path: str) -> bool:
    """단일 파일 잠금 확인 (편의 함수)"""
    checker = FileLockChecker()
    return checker.is_file_locked(path)
