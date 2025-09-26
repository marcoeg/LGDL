import re

PATTERNS = [
    r"ignore previous instructions",
    r"\]\]}>",
    r"<script>.*?</script>",
    r"' OR 1=1"
]

def sanitize(user_input: str):
    cleaned = user_input
    flagged = False
    for p in PATTERNS:
        if re.search(p, cleaned, re.I | re.S):
            flagged = True
            cleaned = re.sub(p, "", cleaned, flags=re.I | re.S)
    return cleaned.strip(), flagged
