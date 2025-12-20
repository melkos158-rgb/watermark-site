p="market.py"
lines=open(p,"r",encoding="utf-8").read().splitlines(True)  # keep \n
out=[]
i=0
changed=0

def is_blank_or_comment(x):
    t=x.strip()
    return (t=="" or t.startswith("#"))

while i < len(lines):
    line = lines[i]
    if line.strip()=="try:":
        j=i+1
        while j < len(lines) and is_blank_or_comment(lines[j]):
            j+=1
        if j < len(lines) and lines[j].lstrip().startswith("except"):
            indent = line[:len(line)-len(line.lstrip())]
            out.append(line)
            out.append(indent+"    pass\n")
            changed += 1
            i += 1
            continue

    out.append(line)
    i += 1

open(p,"w",encoding="utf-8").write("".join(out))
print(f"OK: inserted pass into {changed} empty try blocks")
