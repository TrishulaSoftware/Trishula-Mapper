#!/usr/bin/env python3
"""
Unit tests for Trishula-Mapper.
Uses standard unittest module and mock file setups.
"""

import os
import tempfile
import shutil
import unittest
import json
import ast

# Import trishula_mapper modules directly by path injection
import sys
sys.path.append(r"C:\Users\trish\.gemini\antigravity\scratch")
import trishula_mapper

class TestTrishulaMapper(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for mock codebase
        self.test_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        # Cleanup mock directory
        shutil.rmtree(self.test_dir)

    def test_ast_visitor(self):
        source = """
import os, json
from datetime import datetime as dt
from . import local_mod
from ..parent import parent_mod

class TestClass:
    def __init__(self):
        self.value = 1
    def run_method(self):
        print(self.value)
        os.path.join("a", "b")

def top_function():
    dt.now()
    call_helper()
    
if __name__ == '__main__':
    top_function()
"""
        tree = ast.parse(source)
        visitor = trishula_mapper.CodeInfoVisitor()
        visitor.visit(tree)
        
        # Check imports
        imports = visitor.imports
        self.assertEqual(len(imports), 5) # os, json, datetime, local_mod, parent_mod
        # visitor.visit_Import creates separate entries for os and json
        modules = [imp['module'] for imp in imports]
        self.assertIn('os', modules)
        self.assertIn('json', modules)
        self.assertIn('datetime', modules)
        
        # Check class
        self.assertEqual(len(visitor.classes), 1)
        self.assertEqual(visitor.classes[0]['name'], 'TestClass')
        self.assertIn('__init__', visitor.classes[0]['methods'])
        self.assertIn('run_method', visitor.classes[0]['methods'])
        
        # Check functions
        funcs = [f['name'] for f in visitor.functions]
        self.assertIn('top_function', funcs)
        self.assertIn('__init__', funcs)
        self.assertIn('run_method', funcs)
        
        # Check calls
        calls = [c['name'] for c in visitor.calls]
        self.assertIn('print', calls)
        self.assertIn('os.path.join', calls)
        self.assertIn('dt.now', calls)
        self.assertIn('call_helper', calls)
        self.assertIn('top_function', calls)
        
        # Check main block
        self.assertTrue(visitor.has_main_block)

    def test_resolve_module_path(self):
        # Setup mock files
        # base_dir
        #  ├── a.py
        #  ├── b.py
        #  └── sub
        #       ├── __init__.py
        #       ├── c.py
        #       └── d.py
        a_path = os.path.join(self.test_dir, "a.py")
        b_path = os.path.join(self.test_dir, "b.py")
        sub_dir = os.path.join(self.test_dir, "sub")
        os.makedirs(sub_dir)
        sub_init_path = os.path.join(sub_dir, "__init__.py")
        c_path = os.path.join(sub_dir, "c.py")
        d_path = os.path.join(sub_dir, "d.py")
        
        for p in [a_path, b_path, sub_init_path, c_path, d_path]:
            with open(p, 'w') as f:
                f.write("# empty")
                
        all_files_set = {a_path, b_path, sub_init_path, c_path, d_path}
        
        # Absolute import resolve relative to base
        res = trishula_mapper.resolve_module_path(c_path, 'a', 0, self.test_dir, all_files_set)
        self.assertEqual(res, a_path)
        
        # Absolute import resolve relative to importer's directory
        res = trishula_mapper.resolve_module_path(c_path, 'd', 0, self.test_dir, all_files_set)
        self.assertEqual(res, d_path)
        
        # Relative import from c.py to d.py (from . import d)
        res = trishula_mapper.resolve_module_path(c_path, 'd', 1, self.test_dir, all_files_set)
        self.assertEqual(res, d_path)
        
        # Relative import from c.py to parent folder (from .. import a)
        res = trishula_mapper.resolve_module_path(c_path, 'a', 2, self.test_dir, all_files_set)
        self.assertEqual(res, a_path)
        
        # Relative import from c.py to self sub directory (from . import sub_dir itself -> resolves to __init__.py)
        res = trishula_mapper.resolve_module_path(c_path, '', 1, self.test_dir, all_files_set)
        self.assertEqual(res, sub_init_path)

    def test_circular_dependency_and_dead_code(self):
        # Setup circular dependency:
        # a.py imports b.py
        # b.py imports a.py
        # c.py imports nothing, never imported
        a_path = os.path.join(self.test_dir, "a.py")
        b_path = os.path.join(self.test_dir, "b.py")
        c_path = os.path.join(self.test_dir, "c.py")
        
        with open(a_path, 'w') as f:
            f.write("import b\ndef func_a():\n    pass\n")
        with open(b_path, 'w') as f:
            f.write("import a\ndef func_b():\n    a.func_a()\n")
        with open(c_path, 'w') as f:
            f.write("def func_c():\n    pass\n")
            
        index_data = trishula_mapper.build_index(self.test_dir)
        
        # Verify index structure
        self.assertIn('a.py', index_data['files'])
        self.assertIn('b.py', index_data['files'])
        self.assertIn('c.py', index_data['files'])
        
        # Test imports resolution
        self.assertIn('b.py', index_data['files']['a.py']['local_imports_resolved'])
        self.assertIn('a.py', index_data['files']['b.py']['local_imports_resolved'])
        
        # Test call resolution (b.py calls a.func_a)
        calls_b = index_data['files']['b.py']['calls']
        self.assertEqual(len(calls_b), 1)
        self.assertEqual(calls_b[0]['name'], 'a.func_a')
        self.assertIsNotNone(calls_b[0]['resolved_to'])
        self.assertEqual(calls_b[0]['resolved_to']['file'], 'a.py')
        self.assertEqual(calls_b[0]['resolved_to']['name'], 'func_a')
        
        # Test cycle detection
        cycles = trishula_mapper.find_cycles(index_data)
        self.assertEqual(len(cycles), 1)
        self.assertIn('a.py', cycles[0])
        self.assertIn('b.py', cycles[0])
        
        # Test dead code
        unused_files, unused_defs = trishula_mapper.find_dead_code(index_data)
        # c.py has 0 incoming imports and no main block
        self.assertIn('c.py', unused_files)
        # func_b is never called locally or externally
        # func_c is never called
        # func_a is called by b.py, so it shouldn't be in unused_defs
        unused_names = [d['name'] for d in unused_defs]
        self.assertIn('func_b', unused_names)
        self.assertIn('func_c', unused_names)
        self.assertNotIn('func_a', unused_names)

    def test_advanced_resolutions_and_de_duplication(self):
        # 1. Circular import loop: a -> b -> a
        # Also c -> a (not part of cycle, but imports a)
        # 2. Multiple star imports in main.py: from lib1 import * and from lib2 import *
        # 3. Class method call and self method call in lib1.py
        # 4. CP1252 non-UTF8 file read to check robustness
        
        a_path = os.path.join(self.test_dir, "a.py")
        b_path = os.path.join(self.test_dir, "b.py")
        lib1_path = os.path.join(self.test_dir, "lib1.py")
        lib2_path = os.path.join(self.test_dir, "lib2.py")
        main_path = os.path.join(self.test_dir, "main.py")
        cp1252_path = os.path.join(self.test_dir, "cp1252.py")
        
        with open(a_path, 'w', encoding='utf-8') as f:
            f.write("import b\n")
        with open(b_path, 'w', encoding='utf-8') as f:
            f.write("import a\n")
            
        with open(lib1_path, 'w', encoding='utf-8') as f:
            f.write("\nclass Helper:\n    def __init__(self):\n        self.init_helper()\n    def init_helper(self):\n        pass\n    def unused_method(self):\n        pass\n")
        with open(lib2_path, 'w', encoding='utf-8') as f:
            f.write("def lib2_func():\n    pass\n")
            
        with open(main_path, 'w', encoding='utf-8') as f:
            f.write("\nfrom lib1 import *\nfrom lib2 import *\n\nh = Helper()\nHelper.init_helper(h)\nlib2_func()\n")
        # Write non-UTF-8 CP1252 file with accent characters
        with open(cp1252_path, 'wb') as f:
            f.write(b"# \xe9\xe8\xe0 cp1252 accent\ndef cp1252_func():\n    pass\n")
            
        # Build index
        index_data = trishula_mapper.build_index(self.test_dir)
        
        # Check that cp1252.py was successfully parsed instead of skipped
        self.assertIn('cp1252.py', index_data['files'])
        
        # Check cycles (a.py <-> b.py should only return exactly 1 cycle loop)
        cycles = trishula_mapper.find_cycles(index_data)
        self.assertEqual(len(cycles), 1)
        
        # Check star imports call resolutions
        calls_main = index_data['files']['main.py']['calls']
        resolved_names = {c['name']: c['resolved_to'] for c in calls_main}
        
        # h = Helper() call should resolve to lib1.py Helper
        self.assertIsNotNone(resolved_names.get('Helper'))
        self.assertEqual(resolved_names['Helper']['file'], 'lib1.py')
        self.assertEqual(resolved_names['Helper']['name'], 'Helper')
        
        # lib2_func() call should resolve to lib2.py lib2_func
        self.assertIsNotNone(resolved_names.get('lib2_func'))
        self.assertEqual(resolved_names['lib2_func']['file'], 'lib2.py')
        
        # Helper.init_helper(h) dotted class call should resolve to Helper.init_helper
        self.assertIsNotNone(resolved_names.get('Helper.init_helper'))
        self.assertEqual(resolved_names['Helper.init_helper']['file'], 'lib1.py')
        self.assertEqual(resolved_names['Helper.init_helper']['name'], 'Helper.init_helper')
        
        # Self call `self.init_helper()` in lib1.py should resolve to Helper.init_helper
        calls_lib1 = index_data['files']['lib1.py']['calls']
        resolved_lib1 = {c['name']: c['resolved_to'] for c in calls_lib1}
        self.assertIsNotNone(resolved_lib1.get('self.init_helper'))
        self.assertEqual(resolved_lib1['self.init_helper']['file'], 'lib1.py')
        self.assertEqual(resolved_lib1['self.init_helper']['name'], 'Helper.init_helper')
        
        # Unused definitions should detect Helper.unused_method
        unused_files, unused_defs = trishula_mapper.find_dead_code(index_data)
        unused_methods = [d['name'] for d in unused_defs if d['type'] == 'method']
        self.assertIn('Helper.unused_method', unused_methods)
        self.assertNotIn('Helper.init_helper', unused_methods)

if __name__ == '__main__':
    unittest.main()
