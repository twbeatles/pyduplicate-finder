import os

class EmptyFolderFinder:
    def __init__(self, roots):
        self.roots = roots

    def find_empty_folders(self, check_cancel=None):
        """
        Walks bottom-up and finds directories that contain no files.
        If a directory contains only directories that are also empty, it is considered empty.
        
        Args:
            check_cancel: Optional callback that returns True to cancel the operation
            
        Returns a list of empty folder paths.
        """
        empty_folders = []
        
        # Set to track folders deemed empty so far
        # Since we traverse bottom-up, children are visited before parents
        known_empty = set()
        
        for root_dir in self.roots:
            for dirpath, dirnames, filenames in os.walk(root_dir, topdown=False):
                # 취소 요청 확인
                if check_cancel and check_cancel():
                    return empty_folders  # 중간 결과 반환
                
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
                    
        return empty_folders

    def delete_folders(self, paths):
        deleted = []
        failed = []
        
        # Sort by length descending to delete children before parents
        # This is critical for nested empty folders
        sorted_paths = sorted(paths, key=len, reverse=True)
        
        for p in sorted_paths:
            try:
                os.rmdir(p)
                deleted.append(p)
            except Exception as e:
                failed.append((p, str(e)))
        return deleted, failed
