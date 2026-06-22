# ⚜️ Trishula-Mapper
> **Sovereign Codebase AST Analyzer & Dependency Grapher**

A lightweight, zero-dependency, pure-Python command-line utility built entirely on Python's standard library. It parses codebases using Abstract Syntax Trees (`ast`), maps module-level imports, classes, functions, and cross-file calls, and identifies structural design issues (dead code, circular dependencies).

Designed to run locally and air-gapped with zero network egress risk, keeping code intelligence proprietary and protected.

---

## █ Strategic Alignment & Features
* **Zero Dependencies**: Pure standard library implementation (`ast`, `sys`, `json`, `pathlib`). No external graph libraries or parsers.
* **AST Codebase Parsing**: Deeply indexes directory structures, mapping local modules, resolved imports, functions, classes, and method signatures.
* **Static Analysis Call Graphing**: Traces function and method invocation links to map call chains across files.
* **Dead Code Identification**: Identifies unused classes, uncalled functions/methods, and unimported scripts.
* **Circular Import Detector**: Recursively traverses the import graph to locate circular dependency chains.
* **Mermaid.js Integration**: Automatically translates dependency layers and import flows into Mermaid-compatible diagram code.

---

## █ Installation & Requirements
* **Runtime Environment**: Python 3.10, 3.11, or 3.12 (standard library).
* **Installation**: Drop `trishula_mapper.py` directly into your project root.

---

## █ Usage Reference

### Index a Directory
Scan a codebase and output a structured AST index representation:
```bash
python trishula_mapper.py index --dir /path/to/project --output trishula_graph.json
```

### Trace Callers of a Symbol
Locate all source lines invoking a target function/method:
```bash
python trishula_mapper.py callers <symbol_name>
```

### Module Audit
Inspect module structure, import categories (std-lib vs. external), defined symbols, and local dead code:
```bash
python trishula_mapper.py show <filename.py>
```

### Detect Import Cycles
Find circular imports that cause runtime errors:
```bash
python trishula_mapper.py cycle
```

### Scan for Dead Code
```bash
python trishula_mapper.py dead
```

### Generate Mermaid Dependency Diagrams
```bash
python trishula_mapper.py graph <filename.py> --mermaid
```

---

## █ Proof of Work (Verified Console Output)

The analyzer has been validated against dynamic code mock files to confirm parser accuracy and graph traversal:

```
> python test_trishula_mapper.py
....
----------------------------------------------------------------------
Ran 4 tests in 0.043s

OK
```

---

## █ CI/CD Integration
This repository is configured with a GitHub Actions workflow (`.github/workflows/ci.yml`) validating codebase graph compilation against Python versions `3.10`, `3.11`, and `3.12` on every push to the `main` branch.
