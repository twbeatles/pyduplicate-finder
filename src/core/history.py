import shutil
import tempfile
import os
import atexit
from datetime import datetime
import uuid

# send2trash 라이브러리 (선택적)
try:
    from send2trash import send2trash as send_to_trash
    TRASH_AVAILABLE = True
except ImportError:
    TRASH_AVAILABLE = False


def get_disk_free_space(path):
    """지정된 경로의 디스크 여유 공간 반환 (bytes)"""
    try:
        if hasattr(shutil, 'disk_usage'):
            # Python 3.3+
            usage = shutil.disk_usage(path)
            return usage.free
        else:
            # Fallback for older Python
            return float('inf')  # Skip check if not available
    except:
        return float('inf')  # Skip check on error


class HistoryManager:
    def __init__(self):
        self.undo_stack = []
        self.redo_stack = []
        # 임시 보관소 생성 (OS 임시 폴더 내)
        self.temp_dir = tempfile.mkdtemp(prefix="pydup_trash_")
        # 프로그램 종료 시 자동 정리 등록
        atexit.register(self.cleanup)

    def execute_delete(self, file_paths, progress_callback=None, use_trash=False):
        """
        파일 삭제 실행
        
        Args:
            file_paths: 삭제할 파일 경로 리스트
            progress_callback: 진행률 콜백 함수(current, total)
            use_trash: True면 시스템 휴지통으로 이동 (Undo 불가)
            
        Returns:
            tuple: (success: bool, error_message: str or None)
        """
        if use_trash and TRASH_AVAILABLE:
            return self._delete_to_system_trash(file_paths, progress_callback)
        else:
            return self._delete_to_temp(file_paths, progress_callback)
    
    def check_disk_space(self, file_paths):
        """
        삭제 전 디스크 공간 확인
        
        Args:
            file_paths: 삭제할 파일 경로 리스트
            
        Returns:
            tuple: (has_space: bool, required_bytes: int, available_bytes: int)
        """
        total_size = 0
        for path in file_paths:
            try:
                if os.path.exists(path):
                    total_size += os.path.getsize(path)
            except:
                pass
        
        # 임시 디렉토리의 여유 공간 확인
        available = get_disk_free_space(self.temp_dir)
        
        # 10% 여유 마진 추가
        required_with_margin = int(total_size * 1.1)
        
        return (available >= required_with_margin, total_size, available)
    
    def _delete_to_system_trash(self, file_paths, progress_callback=None):
        """시스템 휴지통으로 파일 이동 (Undo 불가)"""
        success_count = 0
        total_files = len(file_paths)
        
        for idx, path in enumerate(file_paths):
            if os.path.exists(path):
                try:
                    send_to_trash(path)
                    success_count += 1
                except Exception as e:
                    print(f"Trash error: {e}")
            
            if progress_callback:
                progress_callback(idx + 1, total_files)
        
        return success_count > 0
    
    def _delete_to_temp(self, file_paths, progress_callback=None):
        """임시 폴더로 파일 이동 (Undo 가능)"""
        # 디스크 공간 사전 확인
        has_space, required, available = self.check_disk_space(file_paths)
        if not has_space:
            print(f"Warning: Insufficient disk space. Required: {required}, Available: {available}")
            # 경고만 출력하고 진행 (사용자가 판단)
        
        transaction = []
        total_files = len(file_paths)
        
        for idx, original_path in enumerate(file_paths):
            if os.path.exists(original_path):
                try:
                    # 파일명 충돌 방지를 위한 타임스탬프 + UUID 추가
                    filename = os.path.basename(original_path)
                    unique_id = uuid.uuid4().hex[:8]
                    unique_name = f"{int(datetime.now().timestamp())}_{unique_id}_{filename}"
                    backup_path = os.path.join(self.temp_dir, unique_name)
                    
                    shutil.move(original_path, backup_path)
                    transaction.append({'orig': original_path, 'backup': backup_path})
                except Exception as e:
                    print(f"Error moving file: {e}")
            
            if progress_callback:
                progress_callback(idx + 1, total_files)
        
        if transaction:
            self.undo_stack.append(transaction)
            self.redo_stack.clear() # 새로운 동작이 발생하면 Redo 스택 초기화
            return True
        return False
    
    @staticmethod
    def is_trash_available():
        """시스템 휴지통 사용 가능 여부"""
        return TRASH_AVAILABLE


    def undo(self):
        """삭제 취소 (복구)"""
        if not self.undo_stack:
            return None
        
        transaction = self.undo_stack.pop()
        restored_paths = []
        
        for record in transaction:
            try:
                # 백업 파일이 존재하는지 확인
                if not os.path.exists(record['backup']):
                    print(f"Undo Failed: Backup file missing for {record['orig']}")
                    continue

                # 원본 폴더가 없어졌을 수도 있으므로 생성 시도
                parent_dir = os.path.dirname(record['orig'])
                if not os.path.exists(parent_dir):
                    os.makedirs(parent_dir, exist_ok=True)
                
                shutil.move(record['backup'], record['orig'])
                restored_paths.append(record['orig'])
            except Exception as e:
                print(f"Undo Error: {e}")
        
        self.redo_stack.append(transaction)
        return restored_paths

    def redo(self):
        """다시 삭제"""
        if not self.redo_stack:
            return None
            
        transaction = self.redo_stack.pop()
        deleted_paths = []

        for record in transaction:
            try:
                # 원본 파일이 존재하지 않으면 스킵
                if not os.path.exists(record['orig']):
                    print(f"Redo Skip: File not found - {record['orig']}")
                    continue
                shutil.move(record['orig'], record['backup'])
                deleted_paths.append(record['orig'])
            except Exception as e:
                print(f"Redo Error: {e}")
                
        self.undo_stack.append(transaction)
        return deleted_paths

    def cleanup(self):
        """프로그램 종료 시 임시 폴더 정리"""
        try:
            shutil.rmtree(self.temp_dir)
        except:
            pass
