import os
import shutil
from typing import List, Tuple, Optional, Dict, Any
from src.utils.i18n import strings

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
    def __init__(self, cache_manager=None, quarantine_manager=None):
        self.undo_stack = []
        self.redo_stack = []

        # Persistent quarantine backend (does NOT get deleted on exit).
        if quarantine_manager is not None:
            self.quarantine_manager = quarantine_manager
            self.cache_manager = cache_manager
        else:
            # Lazy import to avoid cycles.
            from src.core.cache_manager import CacheManager
            from src.core.quarantine_manager import QuarantineManager
            self.cache_manager = cache_manager or CacheManager()
            self.quarantine_manager = QuarantineManager(self.cache_manager)

    def execute_delete(self, file_paths, progress_callback=None, use_trash=False, check_cancel=None):
        """
        파일 삭제 실행
        
        Args:
            file_paths: 삭제할 파일 경로 리스트
            progress_callback: 진행률 콜백 함수(current, total)
            use_trash: True면 시스템 휴지통으로 이동 (Undo 불가)
            check_cancel: Optional callback that returns True to cancel the operation
            
        Returns:
            tuple: (success: bool, error_message: str or None)
        """
        if use_trash and TRASH_AVAILABLE:
            return self._delete_to_system_trash(file_paths, progress_callback, check_cancel=check_cancel)
        else:
            return self._delete_to_quarantine(file_paths, progress_callback, check_cancel=check_cancel)
    
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
        
        # Quarantine 디렉토리의 여유 공간 확인
        try:
            qdir = self.quarantine_manager.get_quarantine_dir()
        except Exception:
            qdir = os.getcwd()
        available = get_disk_free_space(qdir)
        
        # 10% 여유 마진 추가
        required_with_margin = int(total_size * 1.1)
        
        return (available >= required_with_margin, total_size, available)
    
    def _delete_to_system_trash(self, file_paths, progress_callback=None, check_cancel=None):
        """
        시스템 휴지통으로 파일 이동 (Undo 불가)
        
        Returns:
            tuple: (success: bool, message: str)
        """
        success_count = 0
        failed_files = []
        total_files = len(file_paths)
        cancelled = False
        
        for idx, path in enumerate(file_paths):
            if check_cancel and check_cancel():
                cancelled = True
                break
            if os.path.exists(path):
                try:
                    send_to_trash(path)
                    success_count += 1
                except Exception as e:
                    failed_files.append(os.path.basename(path))
                    print(f"Trash error: {e}")
            
            if progress_callback:
                progress_callback(idx + 1, total_files)
        
        if success_count == 0:
            if cancelled:
                return (False, strings.tr("op_cancelled"))
            return (False, strings.tr("op_trash_move_failed"))
        elif failed_files:
            msg = strings.tr("op_trash_move_partial").format(ok=success_count, total=total_files, failed=len(failed_files))
            if cancelled:
                msg += f" ({strings.tr('op_cancelled')})"
            return (True, msg)
        msg = strings.tr("op_trash_move_done").format(ok=success_count)
        if cancelled:
            msg += f" ({success_count}/{total_files}, {strings.tr('op_cancelled')})"
        return (True, msg)
    
    def _delete_to_quarantine(self, file_paths, progress_callback=None, check_cancel=None):
        """
        Quarantine 폴더로 파일 이동 (Undo 가능, persistent)
        
        Returns:
            tuple: (success: bool, message: str)
        """
        # 디스크 공간 사전 확인
        has_space, required, available = self.check_disk_space(file_paths)
        if not has_space:
            # Issue #1: 디스크 공간 부족 시 실패 반환
            required_mb = required / (1024 * 1024)
            available_mb = available / (1024 * 1024)
            return (False, strings.tr("op_insufficient_space").format(required=required_mb, available=available_mb))
        
        transaction: Dict[str, Any] = {"paths": [], "item_ids": []}
        failed_files = []
        total_files = len(file_paths)
        cancelled = False

        moved, failures = self.quarantine_manager.move_to_quarantine(
            list(file_paths or []),
            progress_callback=(
                (lambda cur, tot, _msg: progress_callback(cur, tot)) if progress_callback else None
            ),
            check_cancel=check_cancel,
        )

        for m in moved:
            transaction["paths"].append(m.orig_path)
            transaction["item_ids"].append(m.item_id)

        for p, reason in failures:
            try:
                failed_files.append(os.path.basename(p))
            except Exception:
                failed_files.append(str(p))
            if reason == "missing":
                continue
            # Keep noisy logs minimal in packaged apps.
            # print(f"Error moving file: {p}: {reason}")
        
        if transaction["item_ids"]:
            self.undo_stack.append(transaction)
            self.redo_stack.clear()  # 새로운 동작이 발생하면 Redo 스택 초기화
            
            if failed_files:
                msg = strings.tr("op_delete_partial").format(
                    ok=len(transaction["item_ids"]), total=total_files, failed=len(failed_files)
                )
                if cancelled:
                    msg += f" ({strings.tr('op_cancelled')})"
                return (True, msg)
            msg = strings.tr("op_delete_done").format(ok=len(transaction["item_ids"]))
            if cancelled:
                msg += f" ({len(transaction['item_ids'])}/{total_files}, {strings.tr('op_cancelled')})"
            return (True, msg)
        
        if cancelled:
            return (False, strings.tr("op_cancelled"))
        return (False, strings.tr("op_no_files_deleted"))
    
    @staticmethod
    def is_trash_available():
        """시스템 휴지통 사용 가능 여부"""
        return TRASH_AVAILABLE


    def undo(self):
        """
        삭제 취소 (복구)
        
        Issue #8: 부분 실패 정보 포함
        
        Returns:
            tuple: (restored_paths: List[str], failed_count: int) or None if stack empty
        """
        if not self.undo_stack:
            return None
        
        transaction = self.undo_stack.pop() or {}
        restored_paths = []
        failed_count = 0

        item_ids = list(transaction.get("item_ids") or [])
        for item_id in item_ids:
            try:
                ok, msg, restored_path = self.quarantine_manager.restore_item(int(item_id))
                if ok:
                    restored_paths.append(restored_path or "")
                else:
                    failed_count += 1
            except Exception:
                failed_count += 1

        # Redo will re-quarantine the restored paths.
        self.redo_stack.append({"paths": list(transaction.get("paths") or []), "item_ids": [], "redo_from_restore": True})
        return (restored_paths, failed_count)

    def redo(self):
        """
        다시 삭제
        
        Issue #8: 부분 실패 정보 포함
        
        Returns:
            tuple: (deleted_paths: List[str], failed_count: int) or None if stack empty
        """
        if not self.redo_stack:
            return None

        transaction = self.redo_stack.pop() or {}
        deleted_paths = []
        failed_count = 0

        paths = list(transaction.get("paths") or [])
        moved, failures = self.quarantine_manager.move_to_quarantine(paths)
        for m in moved:
            deleted_paths.append(m.orig_path)
        failed_count += len([f for f in failures if f and f[0]])

        # Push a new undo transaction based on the new quarantine item ids.
        if moved:
            self.undo_stack.append({"paths": [m.orig_path for m in moved], "item_ids": [m.item_id for m in moved]})

        return (deleted_paths, failed_count)

    # Internal hook: allow OperationWorker to record delete transactions for Ctrl+Z.
    def _record_quarantine_transaction(self, moved_results) -> None:
        try:
            self.undo_stack.append(
                {"paths": [m.orig_path for m in moved_results], "item_ids": [m.item_id for m in moved_results]}
            )
            self.redo_stack.clear()
        except Exception:
            pass
