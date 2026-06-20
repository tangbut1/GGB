import os
import re

def contains_emoji(text):
    # Safe emoji regex (only matches emojis, not CJK)
    emoji_pattern = re.compile(
        "["
        "\U0001f600-\U0001f64f"  # emoticons
        "\U0001f300-\U0001f5ff"  # symbols & pictographs
        "\U0001f680-\U0001f6ff"  # transport & map symbols
        "\U0001f1e0-\U0001f1ff"  # flags (iOS)
        "\u2702-\u27b0"          # Dingbats
        "]+", flags=re.UNICODE)
    return emoji_pattern.search(text) is not None

for root, _, files in os.walk('.'):
    for f in files:
        if not f.endswith(('.py', '.html', '.md')): continue
        if '.git' in root or '__pycache__' in root: continue
        path = os.path.join(root, f)
        try:
            with open(path, 'r', encoding='utf-8') as file:
                lines = file.readlines()
                for i, line in enumerate(lines):
                    if contains_emoji(line):
                        print(f"{path}:{i+1}: {line.strip()}")
        except Exception:
            pass
