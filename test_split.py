from passline.agents.fixer_agent import _split_long_line
from passline.qc.thresholds import LINE_CHAR_MAX_CJK

lines = [
    "Celia, 我们必须跟着我们的感觉走;你是机器人, 而我则想要去太空中爽一下.",
]
for line in lines:
    res = _split_long_line(line, LINE_CHAR_MAX_CJK, True)
    print(res)
