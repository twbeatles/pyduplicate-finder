import sys
import os
import shutil
import unittest
import tempfile
import time

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.history import HistoryManager
from src.core.cache_manager import CacheManager
from src.core.quarantine_manager import QuarantineManager

class TestBackupCollision(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_scan_cache.db")
        self.quarantine_dir = os.path.join(self.test_dir, "quarantine")
        self.cache = CacheManager(db_path=self.db_path)
        self.qm = QuarantineManager(self.cache, quarantine_dir=self.quarantine_dir)
        self.manager = HistoryManager(cache_manager=self.cache, quarantine_manager=self.qm)
        
    def tearDown(self):
        try:
            shutil.rmtree(self.test_dir)
        except:
            pass

    def test_backup_collision(self):
        print("\n[Safety Test] Testing backup filename collisions...")
        
        # Create 20 files with the SAME name in different directories
        # "duplicate.txt"
        files_to_delete = []
        for i in range(20):
            sub_dir = os.path.join(self.test_dir, f"dir_{i}")
            os.makedirs(sub_dir, exist_ok=True)
            filepath = os.path.join(sub_dir, "duplicate.txt")
            with open(filepath, "w") as f:
                f.write(f"content_{i}")
            files_to_delete.append(filepath)
            
        print(f"Created {len(files_to_delete)} duplicate files.")
        
        # Delete them all using the manager
        # Since this happens very fast, timestamp (seconds) will be identical
        res = self.manager.execute_delete(files_to_delete)
        if isinstance(res, tuple):
            success, _message = res
        else:
            success = bool(res)
        self.assertTrue(success)
        
        # Check quarantine dir count
        backup_files = os.listdir(self.quarantine_dir)
        print(f"Backup files found: {len(backup_files)}")
        
        self.assertEqual(len(backup_files), 20, "All files should be backed up uniquely")
        
        # Check integrity (verify unique contents if possible, or just count)
        # Verify undo
        print("Testing Undo...")
        restored = self.manager.undo()
        self.assertIsNotNone(restored)
        if isinstance(restored, tuple):
            restored_paths, failed_count = restored
        else:
            restored_paths, failed_count = restored, 0
        self.assertEqual(failed_count, 0)
        self.assertEqual(len(restored_paths), 20)
        
        for f in files_to_delete:
            self.assertTrue(os.path.exists(f), f"File {f} not restored")

if __name__ == '__main__':
    unittest.main()
