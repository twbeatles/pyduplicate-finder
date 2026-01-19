import shutil
import tempfile
import os
from datetime import datetime

class HistoryManager:
    def __init__(self):
        self.undo_stack = []
        self.redo_stack = []
        # 임시 보관소 생성 (OS 임시 폴더 내)
        self.temp_dir = tempfile.mkdtemp(prefix="pydup_trash_")

    def execute_delete(self, file_paths, progress_callback=None):
        """파일 삭제(임시 이동) 실행"""
        transaction = []
        total_files = len(file_paths)
        
        for idx, original_path in enumerate(file_paths):
            if os.path.exists(original_path):
                try:
                    # 파일명 충돌 방지를 위한 타임스탬프 추가
                    filename = os.path.basename(original_path)
                    unique_name = f"{int(datetime.now().timestamp())}_{filename}"
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
