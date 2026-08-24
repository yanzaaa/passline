def get_width(line):
    from passline.models.subtitle import _strip_markup
    import unicodedata
    visible = _strip_markup(line).rstrip()
    curr_width = 0
    for char in visible:
        w = unicodedata.east_asian_width(char)
        curr_width += 2 if w in ("W", "F") else 1
    return curr_width

cues = [
    "Celia, 我们必须跟着我们的感觉走;",
    "被这些巨型的夺命机械钳追杀..."
]
for c in cues:
    print(c, get_width(c))
