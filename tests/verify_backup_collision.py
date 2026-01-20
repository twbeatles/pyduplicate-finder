import sys
import os
import shutil
import unittest
import tempfile
import time

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.history import HistoryManager

class TestBackupCollision(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.manager = HistoryManager()
        
    def tearDown(self):
        try:
            shutil.rmtree(self.test_dir)
            self.manager.cleanup()
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
        success = self.manager.execute_delete(files_to_delete)
        self.assertTrue(success)
        
        # Check temp dir count
        backup_files = os.listdir(self.manager.temp_dir)
        print(f"Backup files found: {len(backup_files)}")
        
        self.assertEqual(len(backup_files), 20, "All files should be backed up uniquely")
        
        # Check integrity (verify unique contents if possible, or just count)
        # Verify undo
        print("Testing Undo...")
        restored = self.manager.undo()
        self.assertEqual(len(restored), 20)
        
        for f in files_to_delete:
            self.assertTrue(os.path.exists(f), f"File {f} not restored")

if __name__ == '__main__':
    unittest.main()
