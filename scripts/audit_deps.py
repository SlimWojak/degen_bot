#!/usr/bin/env python3
"""
Dependency Audit Script - Phase ε.1 Purification Pass
Lists imported top-level packages vs installed packages.
"""

import ast
import os
import sys
import subprocess
from pathlib import Path
from typing import Set, Dict, List
import importlib.util


def get_installed_packages() -> Set[str]:
    """Get list of installed packages."""
    try:
        result = subprocess.run([sys.executable, '-m', 'pip', 'freeze'], 
                              capture_output=True, text=True, check=True)
        packages = set()
        for line in result.stdout.strip().split('\n'):
            if line and '==' in line:
                package_name = line.split('==')[0].split('[')[0]  # Remove version and extras
                packages.add(package_name.lower())
        return packages
    except subprocess.CalledProcessError:
        return set()


def get_imported_packages(directory: str) -> Set[str]:
    """Get all imported top-level packages from Python files."""
    imported_packages = set()
    
    for py_file in Path(directory).rglob("*.py"):
        if py_file.name.startswith('.') or '__pycache__' in str(py_file):
            continue
            
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content, filename=str(py_file))
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top_level = alias.name.split('.')[0]
                        imported_packages.add(top_level.lower())
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        top_level = node.module.split('.')[0]
                        imported_packages.add(top_level.lower())
                        
        except (SyntaxError, UnicodeDecodeError):
            # Skip files with syntax errors
            continue
    
    return imported_packages


def get_requirements_packages(requirements_file: str) -> Set[str]:
    """Get packages from requirements.txt."""
    packages = set()
    if os.path.exists(requirements_file):
        with open(requirements_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Extract package name (before ==, >=, etc.)
                    package_name = line.split('==')[0].split('>=')[0].split('<=')[0].split('[')[0]
                    packages.add(package_name.lower())
    return packages


def main():
    """Main audit function."""
    print("=== Dependency Audit - Phase ε.1 Purification Pass ===")
    
    # Get packages from different sources
    installed = get_installed_packages()
    imported = get_imported_packages("backend")
    requirements = get_requirements_packages("requirements.txt")
    
    print(f"\n📊 Package Statistics:")
    print(f"  Installed packages: {len(installed)}")
    print(f"  Imported packages: {len(imported)}")
    print(f"  Requirements packages: {len(requirements)}")
    
    # Find missing packages
    missing_from_requirements = imported - requirements
    unused_in_requirements = requirements - imported
    
    print(f"\n🔍 Analysis:")
    print(f"  Missing from requirements: {len(missing_from_requirements)}")
    print(f"  Unused in requirements: {len(unused_in_requirements)}")
    
    if missing_from_requirements:
        print(f"\n❌ Missing from requirements.txt:")
        for pkg in sorted(missing_from_requirements):
            print(f"  - {pkg}")
    
    if unused_in_requirements:
        print(f"\n⚠️  Unused in requirements.txt:")
        for pkg in sorted(unused_in_requirements):
            print(f"  - {pkg}")
    
    # Find phantom packages (installed but not in requirements)
    phantom_packages = installed - requirements
    if phantom_packages:
        print(f"\n👻 Phantom packages (installed but not in requirements):")
        for pkg in sorted(phantom_packages):
            print(f"  - {pkg}")
    
    # Core packages that should be in requirements
    core_packages = {
        'fastapi', 'uvicorn', 'httpx', 'pandas', 'numpy', 
        'pydantic', 'websockets', 'hyperliquid-python-sdk',
        'eth-account', 'web3', 'pytest'
    }
    
    missing_core = core_packages - requirements
    if missing_core:
        print(f"\n🚨 Missing core packages:")
        for pkg in sorted(missing_core):
            print(f"  - {pkg}")
    
    # Generate recommendations
    print(f"\n💡 Recommendations:")
    if missing_from_requirements:
        print(f"  1. Add missing packages to requirements.txt")
    if unused_in_requirements:
        print(f"  2. Remove unused packages from requirements.txt")
    if phantom_packages:
        print(f"  3. Add phantom packages to requirements.txt or remove them")
    
    # Write detailed report
    with open("reports/dependency_diff.txt", "w") as f:
        f.write("=== Dependency Audit Report ===\n\n")
        f.write(f"Installed packages: {len(installed)}\n")
        f.write(f"Imported packages: {len(imported)}\n")
        f.write(f"Requirements packages: {len(requirements)}\n\n")
        
        f.write("Missing from requirements:\n")
        for pkg in sorted(missing_from_requirements):
            f.write(f"  - {pkg}\n")
        
        f.write("\nUnused in requirements:\n")
        for pkg in sorted(unused_in_requirements):
            f.write(f"  - {pkg}\n")
        
        f.write("\nPhantom packages:\n")
        for pkg in sorted(phantom_packages):
            f.write(f"  - {pkg}\n")
    
    print(f"\n📄 Detailed report written to: reports/dependency_diff.txt")
    
    # Return exit code based on issues
    total_issues = len(missing_from_requirements) + len(phantom_packages)
    if total_issues == 0:
        print(f"\n✅ No dependency issues found!")
        return 0
    else:
        print(f"\n⚠️  Found {total_issues} dependency issues")
        return 1


if __name__ == "__main__":
    sys.exit(main())
