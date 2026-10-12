import re

with open(r'c:\Users\NERD-TECH\REF_MILK\refer-milk-main\templates\admin_dashboard.html', 'r', encoding='utf-8') as f:
    orig = f.read()

pattern = r'(<!-- MODAL: [^\n]+ -->.*?)(?=(<!-- MODAL: |<div id="toast"|<script>|$))'
matches = list(re.finditer(pattern, orig, re.DOTALL))
print(f'Matched {len(matches)} modal chunks.')
for idx, m in enumerate(matches):
    first_line = m.group(1).splitlines()[0]
    id_match = re.search(r'id="([^"]+)"', m.group(1))
    modal_id = id_match.group(1) if id_match else 'no-id'
    print(f'{idx+1}: {first_line} -> #{modal_id} ({len(m.group(1))} bytes)')
