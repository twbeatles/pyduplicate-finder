import os
from PySide6.QtCore import QThread, Signal

class EmptyFolderFinder:
    """빈 폴더 탐색기 (동기 버전)"""
    def __init__(self, roots):
        self.roots = roots

    def find_empty_folders(self, check_cancel=None, progress_callback=None):
        """
        Walks bottom-up and finds directories that contain no files.
        If a directory contains only directories that are also empty, it is considered empty.
        
        Args:
            check_cancel: Optional callback that returns True to cancel the operation
            progress_callback: Optional callback(current, total, current_path) for progress
            
        Returns a list of empty folder paths.
        """
        empty_folders = []
        
        # Set to track folders deemed empty so far
        # Since we traverse bottom-up, children are visited before parents
        known_empty = set()
        
        # First, count total directories for progress reporting
        total_dirs = 0
        processed_dirs = 0
        
        if progress_callback:
            for root_dir in self.roots:
                for dirpath, dirnames, filenames in os.walk(root_dir, topdown=False):
                    if check_cancel and check_cancel():
                        break
                    total_dirs += 1
        
        for root_dir in self.roots:
            # Issue #R4: Handle permission errors gracefully with onerror
            for dirpath, dirnames, filenames in os.walk(root_dir, topdown=False, onerror=lambda e: None):
                # 취소 요청 확인
                if check_cancel and check_cancel():
                    return empty_folders  # 중간 결과 반환
                
                processed_dirs += 1
                
                # Progress report
                if progress_callback and processed_dirs % 50 == 0:
                    progress_callback(processed_dirs, total_dirs, dirpath)
                
                # We need to check if all subdirectories are in known_empty
                # But careful: os.walk 'dirnames' list is just names.
                
                # Check 1: Must have no files
                if filenames:
                    continue
                
                # Check 2: All subdirectories must be empty
                all_subdirs_empty = True
                for d in dirnames:
                    full_child_path = os.path.join(dirpath, d)
                    if full_child_path not in known_empty:
                        all_subdirs_empty = False
                        break
                
                if all_subdirs_empty:
                    known_empty.add(dirpath)
                    empty_folders.append(dirpath)
        
        # Final progress
        if progress_callback:
            progress_callback(total_dirs, total_dirs, "Complete")
                    
        return empty_folders

    def delete_folders(self, paths, progress_callback=None):
        """
        Delete the specified folders.
        
        Args:
            paths: List of folder paths to delete
            progress_callback: Optional callback(current, total) for progress
            
        Returns: (deleted_list, failed_list)
        """
        deleted = []
        failed = []
        total = len(paths)
        
        # Sort by length descending to delete children before parents
        # This is critical for nested empty folders
        sorted_paths = sorted(paths, key=len, reverse=True)
        
        for idx, p in enumerate(sorted_paths):
            try:
                os.rmdir(p)
                deleted.append(p)
            except Exception as e:
                failed.append((p, str(e)))
            
            if progress_callback and (idx + 1) % 10 == 0:
                progress_callback(idx + 1, total)
        
        if progress_callback:
            progress_callback(total, total)
            
        return deleted, failed


class EmptyFolderWorker(QThread):
    """빈 폴더 탐색 비동기 워커"""
    progress_updated = Signal(int, str)  # percent, message
    search_finished = Signal(list)  # list of empty folder paths
    
    def __init__(self, roots):
        super().__init__()
        self.roots = roots
        self._stop_requested = False
        self.finder = EmptyFolderFinder(roots)
    
    def stop(self):
        self._stop_requested = True
    
    def run(self):
        try:
            def check_cancel():
                return self._stop_requested
            
            def progress(current, total, path):
                if total > 0:
                    percent = int((current / total) * 100)
                    # Truncate path for display
                    display_path = path if len(path) < 50 else "..." + path[-47:]
                    self.progress_updated.emit(percent, display_path)
            
            results = self.finder.find_empty_folders(
                check_cancel=check_cancel,
                progress_callback=progress
            )
            
            self.search_finished.emit(results)
            
        except Exception as e:
            self.progress_updated.emit(0, f"Error: {e}")
            self.search_finished.emit([])
