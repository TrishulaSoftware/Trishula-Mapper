# Trishula-Mapper

A lightweight, pure-Python command-line utility that indexes Python codebases and maps module imports, classes, functions, and invocation links.

Developed to offer zero-dependency, local codebase scanning with zero network egress.

---

## █ Features
* **Codebase Scanning**: Scans Python source directories to extract abstract syntax trees (ASTs).
* **Import Mapping**: Resolves local module dependencies and flags external package usage.
* **Call Graph Tracking**: Maps functions and classes to where they are invoked.
* **Dead Code Detection**: Identifies unused modules, classes, and functions.
* **Cycle Detection**: Recursively analyzes imports to detect circular dependency loops.
* **Mermaid Integration**: Generates Mermaid-compatible diagrams of codebase dependencies.

---

## █ Installation & Requirements
* **Requirements**: Python 3.10+ (pure standard library, zero third-party requirements).
* **Installation**: Just drop `trishula_mapper.py` into your path or project root.

---

## █ Usage Reference

### 1. Indexing a Codebase
Scan any target directory and write the dependency map to a JSON index file:
```bash
python trishula_mapper.py index --dir /path/to/project --output trishula_graph.json
```

### 2. Finding Callers of a Function/Method
Locate every file and line number where a specific function is invoked:
```bash
python trishula_mapper.py callers <function_name>
```

### 3. Displaying Module Details
Inspect a specific module's imports (Standard Library vs. Third-Party), declared classes, methods, and dead code:
```bash
python trishula_mapper.py show <filename.py>
```

### 4. Detecting Circular Import Loops
Check the entire codebase for circular import cycles:
```bash
python trishula_mapper.py cycle
```

### 5. Listing Dead & Unused Code
Scan the codebase for unreferenced modules, classes, or functions:
```bash
python trishula_mapper.py dead
```

### 6. Generating Mermaid Graphs
Generate a Mermaid diagram block of a module's dependency relationships:
```bash
python trishula_mapper.py graph <filename.py> --mermaid
```

---

## █ Running Tests
To run the included unit test suite:
```bash
python -m unittest test_trishula_mapper.py
```
