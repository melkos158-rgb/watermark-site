out = []
i = 0
import re
import re

PATH = "market.py"

out = []
i = 0

lines = open(PATH, "r", encoding="utf-8").read().splitlines()

while i < len(lines):
    line = lines[i]

    # detect bare try:
    if re.match(r'^\s*try\s*:\s*$', line):
        indent = re.match(r'^(\s*)', line).group(1)

        # check next meaningful line
        j = i + 1
        empty_body = True
        has_handler = False

        while j < len(lines):
            l = lines[j]
            if l.strip() == "":
                j += 1
                continue
            if re.match(rf'^{indent}(except|finally)\b', l):
                has_handler = True
                break
            if not l.startswith(indent + " "):
                break
            empty_body = False
            break

        out.append(line)

        # if try body empty → add pass
        if empty_body:
            out.append(f"{indent}    pass  # auto-fix empty try body")

        # if no except/finally → add except
        if not has_handler:
            out.append(f"{indent}except Exception as e:")
            out.append(f"{indent}    pass  # auto-fix missing except")

        i += 1
        continue

    out.append(line)
    i += 1

open(PATH, "w", encoding="utf-8").write("\n".join(out))
print("✅ Auto-fix done: empty try bodies + orphan except fixed")
