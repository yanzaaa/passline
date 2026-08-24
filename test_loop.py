from passline.models.subtitle import SubtitleCue
cues = [SubtitleCue(index=4, start_ms=0, end_ms=1000, lines=['...你是机器人,', '而我则想要去太空', '中爽一下.'])]
cue = cues[0]
is_cjk = True
limit_line_char = 16

from passline.models.subtitle import _strip_markup
import unicodedata
combined = cue.lines[-2].rstrip() + " " + cue.lines[-1].lstrip()

combined_vis = _strip_markup(combined).rstrip()
width = 0
if is_cjk:
    for char in combined_vis:
        w = unicodedata.east_asian_width(char)
        width += 2 if w in ("W", "F") else 1
else:
    width = len(combined_vis)

print(f"combined='{combined}' width={width} limit={limit_line_char}")
