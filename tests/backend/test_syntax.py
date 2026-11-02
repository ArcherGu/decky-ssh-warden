"""Every Python file in the repository compiles, including those no other test imports."""
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKIP = {".git", "node_modules", "dist", "out", "__pycache__"}


class SyntaxTest(unittest.TestCase):
    def test_every_python_file_compiles(self):
        # dev/cdp.py and scripts/ only run by hand; CI runs this on Decky's Python version.
        paths = []
        for root, dirs, files in os.walk(REPO):
            dirs[:] = [d for d in dirs if d not in SKIP]
            paths += [os.path.join(root, f) for f in files if f.endswith(".py")]
        self.assertIn(os.path.join(REPO, "dev", "cdp.py"), paths)
        for path in paths:
            with self.subTest(os.path.relpath(path, REPO)), open(path, encoding="utf-8") as f:
                compile(f.read(), path, "exec")  # no .pyc written, unlike py_compile
