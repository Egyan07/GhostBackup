"""
utils.py — GhostBackup shared utilities
"""


def fmt_bytes(b: int) -> str:
    if b >= 1024 ** 3: return f"{b / 1024 ** 3:.1f} GB"
    if b >= 1024 ** 2: return f"{b / 1024 ** 2:.1f} MB"
    if b >= 1024:      return f"{b / 1024:.1f} KB"
    return f"{b} B"


def fmt_duration(s: int) -> str:
    if not s: return "\u2014"
    m, sec = divmod(s, 60)
    h, m   = divmod(m, 60)
    if h:  return f"{h}h {m}m {sec}s"
    if m:  return f"{m}m {sec}s"
    return f"{sec}s"
