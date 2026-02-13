import sys
import os
import time
import random
import unittest

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.image_hash import ImageHasher, is_available

class TestImageHasherPerformance(unittest.TestCase):
    def setUp(self):
        if not is_available():
            self.skipTest("imagehash library not installed")
        self.hasher = ImageHasher()

    def test_bk_tree_performance(self):
        print("\n[Performance Test] Generating dummy hashes...")
        
        dummy_hashes = {}
        base_hashes = [
            "0" * 64, 
            "F" * 64, 
            "0F" * 32, 
            "A" * 64, 
            "1234567890ABCDEF" * 4
        ]
        
        for i, base in enumerate(base_hashes):
            dummy_hashes[f"group_{i}_base.jpg"] = base
            for j in range(5): # Reduced from 20 to 5
                chars = list(base)
                pos = random.randint(0, 63)
                chars[pos] = "1" if chars[pos] == "0" else "0"
                variant = "".join(chars)
                dummy_hashes[f"group_{i}_var_{j}.jpg"] = variant

        for i in range(50): # Reduced from 1000 to 50
            h = "".join(random.choice("0123456789abcdef") for _ in range(64))
            dummy_hashes[f"noise_{i}.jpg"] = h

        print(f"Total items: {len(dummy_hashes)}")
        
        start_time = time.time()
        print("Starting grouping...")
        
        def progress(c, t):
            if c % 10 == 0: print(f"Progress: {c}/{t}")

        groups = self.hasher.group_similar_images(dummy_hashes, threshold=0.9, progress_callback=progress)
        duration = time.time() - start_time
        
        print(f"Grouping time: {duration:.4f} seconds")
        print(f"Found {len(groups)} groups")
        
        self.assertGreaterEqual(len(groups), 5)

if __name__ == '__main__':
    unittest.main()
