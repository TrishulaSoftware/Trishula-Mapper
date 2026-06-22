#!/usr/bin/env python3
"""
Trishula-Mapper
Sovereign AST Codebase Dependency Grapher

A pure-Python codebase navigation and indexing utility. Recursively scans
directories, parses python ASTs, resolves local imports/calls, and provides
graph query capabilities (cycle detection, dead code, callers, and Mermaid).
"""

import os
import sys
import ast
import json
import argparse

class CodeInfoVisitor(ast.NodeVisitor):
    def __init__(self):
        self.imports = []
        self.classes = []
        self.functions = []
        self.calls = []
        self.scope_stack = ['module']
        self.has_main_block = False

    def visit_Import(self, node):
        for name in node.names:
            self.imports.append({
                'module': name.name,
                'asname': name.asname,
                'names': None,
                'line': node.lineno,
                'level': 0
            })
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module if node.module else ''
        names = []
        for n in node.names:
            names.append({
                'name': n.name,
                'asname': n.asname
            })
        self.imports.append({
            'module': module,
            'names': names,
            'line': node.lineno,
            'level': node.level or 0
        })
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        methods = []
        for body_node in node.body:
            if isinstance(body_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(body_node.name)
        
        self.classes.append({
            'name': node.name,
            'methods': methods,
            'line': node.lineno
        })
        
        self.scope_stack.append(f"class:{node.name}")
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_FunctionDef(self, node):
        current_scope = self.scope_stack[-1]
        is_method = current_scope.startswith("class:")
        is_nested = current_scope.startswith("function:")
        
        self.functions.append({
            'name': node.name,
            'line': node.lineno,
            'is_method': is_method,
            'is_nested': is_nested,
            'class_name': current_scope.split(":", 1)[1] if is_method else None
        })
        
        self.scope_stack.append(f"function:{node.name}")
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_AsyncFunctionDef(self, node):
        current_scope = self.scope_stack[-1]
        is_method = current_scope.startswith("class:")
        is_nested = current_scope.startswith("function:")
        
        self.functions.append({
            'name': node.name,
            'line': node.lineno,
            'is_method': is_method,
            'is_nested': is_nested,
            'class_name': current_scope.split(":", 1)[1] if is_method else None
        })
        
        self.scope_stack.append(f"function:{node.name}")
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_Call(self, node):
        func_name = self._get_func_name(node.func)
        if func_name:
            self.calls.append({
                'name': func_name,
                'line': node.lineno
            })
        self.generic_visit(node)

    def visit_If(self, node):
        # Check for `if __name__ == '__main__':`
        if isinstance(node.test, ast.Compare):
            left = node.test.left
            if isinstance(left, ast.Name) and left.id == '__name__':
                for op in node.test.ops:
                    if isinstance(op, ast.Eq):
                        for comparator in node.test.comparators:
                            if isinstance(comparator, ast.Constant) and comparator.value == '__main__':
                                self.has_main_block = True
                            elif isinstance(comparator, ast.Str) and comparator.s == '__main__': # Python < 3.8
                                self.has_main_block = True
        self.generic_visit(node)

    def _get_func_name(self, node):
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            base = self._get_func_name(node.value)
            if base:
                return f"{base}.{node.attr}"
            return node.attr
        return None

def resolve_module_path(importer_abs_path, import_name, level, base_dir, all_files_set):
    importer_dir = os.path.dirname(importer_abs_path)
    
    # 1. Handle relative imports
    if level > 0:
        curr_dir = importer_dir
        for _ in range(level - 1):
            curr_dir = os.path.dirname(curr_dir)
        
        if not import_name:
            init_py = os.path.join(curr_dir, "__init__.py")
            if init_py in all_files_set:
                return init_py
            return None
        
        module_rel_path = import_name.replace('.', os.sep)
        target_path_base = os.path.join(curr_dir, module_rel_path)
        
        target_py = target_path_base + ".py"
        if target_py in all_files_set:
            return target_py
        target_init = os.path.join(target_path_base, "__init__.py")
        if target_init in all_files_set:
            return target_init
        return None
        
    # 2. Handle absolute imports
    if not import_name:
        return None
        
    module_rel_path = import_name.replace('.', os.sep)
    
    # Check relative to importer_dir first
    target_path_base = os.path.join(importer_dir, module_rel_path)
    target_py = target_path_base + ".py"
    if target_py in all_files_set:
        return target_py
    target_init = os.path.join(target_path_base, "__init__.py")
    if target_init in all_files_set:
        return target_init
        
    # Check relative to base_dir
    target_path_base = os.path.join(base_dir, module_rel_path)
    target_py = target_path_base + ".py"
    if target_py in all_files_set:
        return target_py
    target_init = os.path.join(target_path_base, "__init__.py")
    if target_init in all_files_set:
        return target_init
        
    return None

def build_index(target_dir):
    target_dir = os.path.abspath(target_dir)
    all_files = []
    for root, _, files in os.walk(target_dir):
        # Exclude common directories to avoid noise
        if any(x in root.split(os.sep) for x in ['.git', '__pycache__', 'venv', '.agents', 'logo_cache', 'third_party']):
            continue
        for file in files:
            if file.endswith('.py'):
                all_files.append(os.path.join(root, file))
                
    all_files_set = set(all_files)
    
    # Get standard library names
    STD_LIBS = set()
    if hasattr(sys, 'stdlib_module_names'):
        STD_LIBS.update(sys.stdlib_module_names)
    STD_LIBS.update(sys.builtin_module_names)
    
    # First pass: parse AST for all files
    raw_data = {}
    for file_path in all_files:
        rel_path = os.path.relpath(file_path, target_dir).replace(os.sep, '/')
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
            tree = ast.parse(source, filename=file_path)
            visitor = CodeInfoVisitor()
            visitor.visit(tree)
            raw_data[rel_path] = {
                'abs_path': file_path,
                'visitor': visitor
            }
        except Exception as e:
            # Skip files that fail to parse
            print(f"Warning: Failed to parse {rel_path}: {e}", file=sys.stderr)
            
    # Second pass: resolve imports, calls, and build bindings
    index = {
        'base_dir': target_dir.replace(os.sep, '/'),
        'files': {}
    }
    
    # Create module_to_file mapping
    module_to_file = {}
    for rel_path, data in raw_data.items():
        # E.g. foo/bar.py -> foo.bar, if __init__.py -> foo
        parts = rel_path[:-3].split('/')
        if parts[-1] == '__init__':
            parts.pop()
        module_name = '.'.join(parts)
        module_to_file[module_name] = rel_path
        if len(parts) == 1:
            # Also register name directly
            module_to_file[parts[0]] = rel_path

    # Process each file
    for rel_path, data in raw_data.items():
        visitor = data['visitor']
        abs_path = data['abs_path']
        
        resolved_imports = []
        external_imports = set()
        local_imports_resolved = set()
        
        # Build local name bindings
        local_bindings = {}
        
        # 1. Local definitions
        for func in visitor.functions:
            if not func['is_method'] and not func['is_nested']:
                local_bindings[func['name']] = ('local_func', rel_path, func['name'])
        for cls in visitor.classes:
            local_bindings[cls['name']] = ('local_class', rel_path, cls['name'])
            
        # 2. Imports
        for imp in visitor.imports:
            # Resolve the module
            resolved_abs = resolve_module_path(abs_path, imp['module'], imp['level'], target_dir, all_files_set)
            
            if resolved_abs:
                resolved_rel = os.path.relpath(resolved_abs, target_dir).replace(os.sep, '/')
                local_imports_resolved.add(resolved_rel)
                
                imp_entry = {
                    'module': imp['module'],
                    'resolved_rel': resolved_rel,
                    'line': imp['line'],
                    'level': imp['level'],
                    'names': imp['names']
                }
                resolved_imports.append(imp_entry)
                
                # Bindings for `import A` or `import A as B`
                if imp['names'] is None:
                    # Bind the imported module name
                    bound_name = imp['asname'] if imp['asname'] else imp['module'].split('.')[0]
                    local_bindings[bound_name] = ('module', resolved_rel, None)
                else:
                    # Bind specific names `from A import x, y`
                    for n in imp['names']:
                        bound_name = n['asname'] if n['asname'] else n['name']
                        if n['name'] == '*':
                            local_bindings['*'] = ('star', resolved_rel, None)
                        else:
                            local_bindings[bound_name] = ('member', resolved_rel, n['name'])
            else:
                external_imports.add(imp['module'])
                
        # Resolve calls using bindings
        resolved_calls = []
        for call in visitor.calls:
            call_name = call['name']
            resolved_target = None
            
            # Simple name lookup
            if '.' not in call_name:
                if call_name in local_bindings:
                    binding = local_bindings[call_name]
                    if binding[0] in ['local_func', 'local_class']:
                        resolved_target = {'type': 'local', 'file': binding[1], 'name': binding[2]}
                    elif binding[0] == 'member':
                        resolved_target = {'type': 'local', 'file': binding[1], 'name': binding[2]}
                elif '*' in local_bindings:
                    # Check if defined in star-imported module
                    star_file = local_bindings['*'][1]
                    if star_file in raw_data:
                        star_visitor = raw_data[star_file]['visitor']
                        # Check if function or class is defined there
                        defined = False
                        for f in star_visitor.functions:
                            if f['name'] == call_name and not f['is_method'] and not f['is_nested']:
                                defined = True
                                break
                        for c in star_visitor.classes:
                            if c['name'] == call_name:
                                defined = True
                                break
                        if defined:
                            resolved_target = {'type': 'local', 'file': star_file, 'name': call_name}
            else:
                # Dotted name lookup
                parts = call_name.split('.')
                prefix = parts[0]
                if prefix in local_bindings:
                    binding = local_bindings[prefix]
                    if binding[0] == 'module':
                        target_file = binding[1]
                        member_name = '.'.join(parts[1:])
                        resolved_target = {'type': 'local', 'file': target_file, 'name': member_name}
            
            resolved_calls.append({
                'name': call_name,
                'line': call['line'],
                'resolved_to': resolved_target
            })

        std_imports = set()
        third_party_imports = set()
        for ext in external_imports:
            top_pkg = ext.split('.')[0]
            if top_pkg in STD_LIBS:
                std_imports.add(ext)
            else:
                third_party_imports.add(ext)

        index['files'][rel_path] = {
            'abs_path': abs_path.replace(os.sep, '/'),
            'module_name': '.'.join(rel_path[:-3].split('/')).replace('.__init__', ''),
            'has_main_block': visitor.has_main_block,
            'imports': resolved_imports,
            'external_imports': sorted(list(external_imports)),
            'std_imports': sorted(list(std_imports)),
            'third_party_imports': sorted(list(third_party_imports)),
            'local_imports_resolved': sorted(list(local_imports_resolved)),
            'classes': visitor.classes,
            'functions': [f for f in visitor.functions if not f['is_nested']],
            'calls': resolved_calls
        }
        
    return index

def find_cycles(index_data):
    graph = {f: data['local_imports_resolved'] for f, data in index_data['files'].items()}
    visited = {} # None: unvisited, 0: visiting, 1: visited
    cycles = []
    
    def dfs(node, path):
        visited[node] = 0
        path.append(node)
        for neighbor in graph.get(node, []):
            if neighbor not in index_data['files']:
                continue
            if visited.get(neighbor) == 0:
                cycle_start_idx = path.index(neighbor)
                cycles.append(path[cycle_start_idx:] + [neighbor])
            elif neighbor not in visited:
                dfs(neighbor, path)
        path.pop()
        visited[node] = 1

    for node in graph:
        if node not in visited:
            dfs(node, [])
            
    return cycles

def find_dead_code(index_data):
    all_files = set(index_data['files'].keys())
    
    # 1. Incoming imports count
    incoming_imports = {f: set() for f in all_files}
    for file, data in index_data['files'].items():
        for dep in data['local_imports_resolved']:
            if dep in incoming_imports:
                incoming_imports[dep].add(file)
                
    unused_files = []
    for file, importers in incoming_imports.items():
        if not importers and not index_data['files'][file]['has_main_block']:
            # Never imported and has no if __name__ == '__main__':
            unused_files.append(file)
            
    # 2. Unused functions/classes
    # Build a map of all calls across all files
    all_calls = []
    for file, data in index_data['files'].items():
        for call in data['calls']:
            if call['resolved_to'] and call['resolved_to']['type'] == 'local':
                all_calls.append((file, call['resolved_to']['file'], call['resolved_to']['name']))
                
    # Build incoming callers
    incoming_callers = {} # (target_file, target_name) -> list of source_file
    for src, target_file, target_name in all_calls:
        key = (target_file, target_name)
        if key not in incoming_callers:
            incoming_callers[key] = []
            if src not in incoming_callers[key]:
                incoming_callers[key].append(src)
                
    unused_definitions = []
    for file, data in index_data['files'].items():
        # Top level functions
        for func in data['functions']:
            if func['is_method']:
                continue
            name = func['name']
            if name.startswith('__') or name == 'main':
                continue
            # Check if called anywhere (locally or externally)
            called_internally = False
            for call in data['calls']:
                if call['resolved_to'] and call['resolved_to']['file'] == file and call['resolved_to']['name'] == name:
                    called_internally = True
                    break
            called_externally = (file, name) in incoming_callers
            if not called_internally and not called_externally:
                unused_definitions.append({
                    'type': 'function',
                    'file': file,
                    'name': name,
                    'line': func['line']
                })
                
        # Classes
        for cls in data['classes']:
            name = cls['name']
            called_internally = False
            for call in data['calls']:
                if call['resolved_to'] and call['resolved_to']['file'] == file and call['resolved_to']['name'] == name:
                    called_internally = True
                    break
            called_externally = (file, name) in incoming_callers
            if not called_internally and not called_externally:
                unused_definitions.append({
                    'type': 'class',
                    'file': file,
                    'name': name,
                    'line': cls['line']
                })
                
    return sorted(unused_files), sorted(unused_definitions, key=lambda x: (x['file'], x['line']))

def print_ascii_tree(file, index_data, prefix="", is_last=True, visited=None):
    if visited is None:
        visited = set()
    
    branch = '└── ' if is_last else '├── '
    line = f"{prefix}{branch}{file}"
    if file not in index_data['files']:
        line += " [EXTERNAL]"
        
    try:
        print(line)
    except UnicodeEncodeError:
        # Fallback to pure ASCII characters for non-unicode console configurations
        ascii_prefix = prefix.replace('│', '|')
        ascii_branch = '\\-- ' if is_last else '|-- '
        ascii_line = f"{ascii_prefix}{ascii_branch}{file}"
        if file not in index_data['files']:
            ascii_line += " [EXTERNAL]"
        print(ascii_line)
    
    if file not in index_data['files']:
        return
        
    if file in visited:
        # Avoid infinite loops on circular imports
        return
    visited.add(file)
    
    deps = index_data['files'][file]['local_imports_resolved']
    prefix += "    " if is_last else "│   "
    for i, dep in enumerate(deps):
        print_ascii_tree(dep, index_data, prefix, i == len(deps) - 1, visited)

def print_mermaid(index_data, root_file=None):
    print("```mermaid")
    print("graph TD")
    
    # Track written connections
    connections = set()
    files_to_print = set()
    
    if root_file:
        # Only print subgraph reachable from root_file
        def gather(node, visited):
            if node in visited:
                return
            visited.add(node)
            if node in index_data['files']:
                for dep in index_data['files'][node]['local_imports_resolved']:
                    gather(dep, visited)
        visited = set()
        gather(root_file, visited)
        files_to_print = visited
    else:
        files_to_print = set(index_data['files'].keys())

    for f in files_to_print:
        # Print nodes with safe IDs
        safe_id = f.replace('.', '_').replace('/', '_').replace('-', '_')
        print(f"    {safe_id}[\"{f}\"]")

    for file in files_to_print:
        if file not in index_data['files']:
            continue
        safe_src = file.replace('.', '_').replace('/', '_').replace('-', '_')
        for dep in index_data['files'][file]['local_imports_resolved']:
            if dep not in files_to_print:
                continue
            safe_dep = dep.replace('.', '_').replace('/', '_').replace('-', '_')
            conn = (safe_src, safe_dep)
            if conn not in connections:
                connections.add(conn)
                print(f"    {safe_src} --> {safe_dep}")
    print("```")

def main():
    parser = argparse.ArgumentParser(description="Trishula-Mapper: Pure Python Codebase Dependency Grapher")
    subparsers = parser.add_subparsers(dest='subcommand', required=True)
    
    # 1. index
    parser_index = subparsers.add_parser('index', help='Scan codebase directory and index dependencies')
    parser_index.add_argument('--dir', default='.', help='Codebase directory to scan')
    parser_index.add_argument('--output', default='trishula_graph.json', help='Output index JSON path')
    
    # 2. show
    parser_show = subparsers.add_parser('show', help='Show detailed info for a file')
    parser_show.add_argument('file', help='Target file path')
    parser_show.add_argument('--index', default='trishula_graph.json', help='Index JSON path')
    
    # 3. callers
    parser_callers = subparsers.add_parser('callers', help='Find callers of a function/class')
    parser_callers.add_argument('func', help='Target function or class name')
    parser_callers.add_argument('--index', default='trishula_graph.json', help='Index JSON path')
    
    # 4. cycle
    parser_cycle = subparsers.add_parser('cycle', help='Detect circular import loops')
    parser_cycle.add_argument('--index', default='trishula_graph.json', help='Index JSON path')
    
    # 5. dead
    parser_dead = subparsers.add_parser('dead', help='Find unused modules and functions')
    parser_dead.add_argument('--index', default='trishula_graph.json', help='Index JSON path')
    
    # 6. graph
    parser_graph = subparsers.add_parser('graph', help='Render codebase dependency graph')
    parser_graph.add_argument('file', nargs='?', default=None, help='Optional root file')
    parser_graph.add_argument('--mermaid', action='store_true', help='Output in Mermaid diagram format')
    parser_graph.add_argument('--index', default='trishula_graph.json', help='Index JSON path')

    args = parser.parse_args()
    
    if args.subcommand == 'index':
        print(f"Scanning codebase in {args.dir}...")
        idx = build_index(args.dir)
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(idx, f, indent=2)
        print(f"Successfully indexed {len(idx['files'])} files. Saved index to {args.output}")
        return

    # Load index file for other commands
    if not os.path.exists(args.index):
        print(f"Error: Index file '{args.index}' does not exist. Run 'index' command first.", file=sys.stderr)
        sys.exit(1)
        
    with open(args.index, 'r', encoding='utf-8') as f:
        idx_data = json.load(f)
        
    if args.subcommand == 'show':
        target = args.file.replace(os.sep, '/')
        if target not in idx_data['files']:
            # Search case-insensitive or by basename
            matched = None
            for f in idx_data['files']:
                if os.path.basename(f) == os.path.basename(target) or target.lower() in f.lower():
                    matched = f
                    break
            if matched:
                target = matched
            else:
                print(f"Error: File '{args.file}' not found in index.", file=sys.stderr)
                sys.exit(1)
                
        data = idx_data['files'][target]
        
        # Calculate dead status for classes/functions in target
        unused_files, unused_defs = find_dead_code(idx_data)
        dead_set = {(d['file'], d['name']) for d in unused_defs}
        
        print(f"==================================================")
        print(f"Module: {data['module_name']}")
        print(f"File:   {target}")
        print(f"==================================================")
        print(f"Local Imports Resolved:")
        for dep in data['local_imports_resolved']:
            print(f"  - {dep}")
        
        std_imp = data.get('std_imports', [])
        tp_imp = data.get('third_party_imports', [])
        
        if std_imp:
            print(f"\nStandard Library Imports:")
            for dep in std_imp:
                print(f"  - {dep}")
        if tp_imp:
            print(f"\nThird-Party Imports:")
            for dep in tp_imp:
                print(f"  - {dep}")
        if not std_imp and not tp_imp:
            print(f"\nExternal Imports:")
            for dep in data['external_imports']:
                print(f"  - {dep}")
                
        print(f"\nClasses Declared:")
        for cls in data['classes']:
            is_dead = (target, cls['name']) in dead_set
            dead_tag = " [DEAD]" if is_dead else ""
            print(f"  - {cls['name']}{dead_tag} (line {cls['line']})")
            for m in cls['methods']:
                print(f"      . {m}")
        print(f"\nFunctions Declared:")
        for func in data['functions']:
            is_dead = (target, func['name']) in dead_set
            dead_tag = " [DEAD]" if is_dead else ""
            print(f"  - {func['name']}{dead_tag} (line {func['line']})")
        print(f"==================================================")
        
    elif args.subcommand == 'callers':
        target_name = args.func
        found = False
        print(f"Callers of '{target_name}':")
        for file, data in idx_data['files'].items():
            for call in data['calls']:
                resolved = call['resolved_to']
                if resolved and resolved['type'] == 'local' and resolved['name'] == target_name:
                    print(f"  - {file}:{call['line']} (via Call '{call['name']}')")
                    found = True
        if not found:
            print("  No callers found.")
            
    elif args.subcommand == 'cycle':
        cycles = find_cycles(idx_data)
        if not cycles:
            print("No circular import loops detected. Codebase is clean!")
        else:
            print(f"Detected {len(cycles)} circular import loops:")
            for i, c in enumerate(cycles, 1):
                path_str = ' -> '.join(c)
                print(f"  {i}. {path_str}")
                
    elif args.subcommand == 'dead':
        unused_files, unused_defs = find_dead_code(idx_data)
        print("==================================================")
        print(f"Unused/Orphaned Python Files (never imported):")
        print("==================================================")
        if not unused_files:
            print("  None")
        else:
            for f in unused_files:
                print(f"  - {f}")
                
        print("\n==================================================")
        print(f"Unused Class/Function Definitions (never called):")
        print("==================================================")
        if not unused_defs:
            print("  None")
        else:
            for d in unused_defs:
                print(f"  - {d['file']}:{d['line']} ({d['type']} '{d['name']}')")
                
    elif args.subcommand == 'graph':
        if args.file:
            root = args.file.replace(os.sep, '/')
            if root not in idx_data['files']:
                matched = None
                for f in idx_data['files']:
                    if os.path.basename(f) == os.path.basename(root) or root.lower() in f.lower():
                        matched = f
                        break
                if matched:
                    root = matched
                else:
                    print(f"Error: File '{args.file}' not found in index.", file=sys.stderr)
                    sys.exit(1)
        else:
            root = None
            
        if args.mermaid:
            print_mermaid(idx_data, root)
        else:
            if root:
                print_ascii_tree(root, idx_data, prefix="", is_last=True)
            else:
                incoming = {f: 0 for f in idx_data['files']}
                for f, data in idx_data['files'].items():
                    for dep in data['local_imports_resolved']:
                        if dep in incoming:
                            incoming[dep] += 1
                roots = [f for f, count in incoming.items() if count == 0]
                for r in roots:
                    print_ascii_tree(r, idx_data, prefix="", is_last=True)

if __name__ == '__main__':
    main()
