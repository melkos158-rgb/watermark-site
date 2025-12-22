# tools/dev_audit_fix.py
"""
Helper script for dev_audit_fix.ps1:
- --fix-indentation: Fix indentation errors in a file at a given line (convert tabs to 4 spaces in affected block)
- --fix-tests: Convert real server tests to Flask test client style (minimal edits)
"""
import argparse
import re
import sys
from pathlib import Path

def fix_indentation(file, line):
    path = Path(file)
    lines = path.read_text(encoding='utf-8').splitlines()
    idx = int(line) - 1
    # Find block start (def/if/try/class)
    block_start = idx
    while block_start > 0 and not re.match(r'^(\s*)(def |if |try:|class )', lines[block_start]):
        block_start -= 1
    # Convert tabs to 4 spaces in block
    changed = False
    for i in range(block_start, min(len(lines), block_start+20)):
        if lines[i].startswith('\t') or '\t' in lines[i]:
            lines[i] = lines[i].replace('\t', '    ')
            changed = True
        if i > idx+10:
            break
    if changed:
        path.write_text('\n'.join(lines)+"\n", encoding='utf-8')
        print(f"Fixed indentation in {file} at block starting line {block_start+1}")
    else:
        print(f"No tabs found to fix in {file} near line {line}")

def fix_tests():
    # Only a minimal implementation: scan for requests.get(BASE_URL+...) and replace with client.get(...)
    import glob
    for testfile in glob.glob('test_*.py') + glob.glob('tests/test_*.py'):
        with open(testfile, encoding='utf-8') as f:
            code = f.read()
        if 'requests.get(BASE_URL' in code:
            code = re.sub(r'requests\.get\(BASE_URL \+ ([^\)]+)\)', r'client.get(\1)', code)
            code = re.sub(r'requests\.post\(BASE_URL \+ ([^\)]+)\)', r'client.post(\1)', code)
            # Add client fixture if missing
            if 'def client(' not in code:
                code = ("import pytest\nfrom app import create_app\n\n@pytest.fixture\ndef client():\n    app = create_app()\n    return app.test_client()\n\n" + code)
            with open(testfile, 'w', encoding='utf-8') as f:
                f.write(code)
            print(f"Converted {testfile} to Flask test client style.")
        else:
            print(f"No real server calls found in {testfile}.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fix-indentation', action='store_true')
    parser.add_argument('--fix-tests', action='store_true')
    parser.add_argument('--file')
    parser.add_argument('--line')
    args = parser.parse_args()
    if args.fix_indentation and args.file and args.line:
        fix_indentation(args.file, args.line)
    elif args.fix_tests:
        fix_tests()
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == '__main__':
    main()
