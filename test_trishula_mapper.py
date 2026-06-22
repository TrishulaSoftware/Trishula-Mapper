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

if __name__ == '__main__':
    unittest.main()
