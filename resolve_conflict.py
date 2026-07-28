import json
import re

with open("backend/audit_log.json", "r", encoding="utf-8") as f:
    content = f.read()

# We need to extract all the JSON objects from the conflicting parts and combine them
# The array begins with [ and ends with ]
# So we can just find all objects matching the structure

def fix_conflict(content):
    # Just grab all the objects between <<<<<<< HEAD and =======
    head_match = re.search(r'<<<<<<< HEAD\n(.*?)\n=======', content, re.DOTALL)
    if not head_match:
        return content
    head_content = head_match.group(1)

    # Grab objects between ======= and >>>>>>> hash
    incoming_match = re.search(r'=======\n(.*?)>>>>>>> [a-f0-9]+', content, re.DOTALL)
    incoming_content = incoming_match.group(1)
    
    # Both sides were split inside an object! 
    # Notice the split point:
    # "target": "usr_c1c9ccc985e6",
    # =======
    # "id": "audit_3585f5ecc1e0",
    
    # Actually, in HEAD it ends with:
    #    "target": "usr_c1c9ccc985e6",
    # And in incoming it starts with:
    #    "id": "audit_3585f5ecc1e0",
    # But wait, looking at the previous object in HEAD:
    #  {
    #    "id": "audit_dd1b3846d301",
    #    ...
    #    "target": "usr_c1c9ccc985e6",
    
    # So the HEAD side lacks "details": {} and }
    
    head_fixed = head_content + ',\n    "details": {}\n  },'
    
    # For incoming, it starts at "id": ...
    # We need to prepend {
    incoming_fixed = '\n  {\n' + incoming_content
    
    combined = head_fixed + incoming_fixed
    
    new_content = content[:head_match.start()] + combined + content[incoming_match.end():]
    return new_content

new_content = fix_conflict(content)
with open("backend/audit_log.json", "w", encoding="utf-8") as f:
    f.write(new_content)

# Let's verify it's valid JSON
try:
    with open("backend/audit_log.json", "r", encoding="utf-8") as f:
        json.load(f)
    print("Valid JSON!")
except Exception as e:
    print(f"Error parsing JSON: {e}")

