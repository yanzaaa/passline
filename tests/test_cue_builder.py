import pytest
from passline.origination.cue_builder import build_cues, TranscriptSegment
from passline.qc.rules import check_file

def test_en_multiline_split():
    # 20 English words, each ~0.3s
    segments = []
    start = 0.0
    for i in range(20):
        # Use short words to keep CPS naturally low and avoid unfixable density
        segments.append(TranscriptSegment(word="word", start_s=start, end_s=start+0.3))
        start += 0.3
    
    sf = build_cues(segments, language="en")
    for cue in sf.cues:
        assert len(cue.lines) <= 2
        for line in cue.lines:
            assert len(line) <= 42
            
    findings = check_file(sf)
    assert not [f for f in findings if f.severity == "ERROR"]

def test_zh_cjk_column_budget():
    # 30 Mandarin characters, each ~0.3s
    segments = []
    start = 0.0
    for i in range(30):
        # space them by 0.3s so 2 chars per 0.3s => ~6.6 CPS (safe)
        segments.append(TranscriptSegment(word=f"字", start_s=start, end_s=start+0.3))
        start += 0.3
        
    sf = build_cues(segments, language="zh")
    for cue in sf.cues:
        assert len(cue.lines) <= 2
        for line in cue.lines:
            # width <= 16
            width = sum(2 for _ in line)
            assert width <= 16
            
    findings = check_file(sf)
    assert not [f for f in findings if f.severity == "ERROR"]

def test_minimum_duration_enforcement():
    segments = [TranscriptSegment(word="Stop", start_s=1.0, end_s=1.2)]
    sf = build_cues(segments, language="en")
    assert sf.cues[0].duration_ms >= 1000

def test_overlap_prevention():
    segments = [
        TranscriptSegment(word="Wait", start_s=1.0, end_s=1.5),
        TranscriptSegment(word="Go", start_s=3.5, end_s=4.5)
    ]
    # Set min_duration so "Wait" becomes 3.0s, which is 1.0 -> 4.0.
    # But "Go" starts at 3.5. So "Wait" must end at 3.499.
    sf = build_cues(segments, language="en", min_duration_ms=3000) 
    
    cues = sf.cues
    assert cues[0].end_ms < cues[1].start_ms
    findings = check_file(sf)
    overlap = [f for f in findings if f.rule == "overlapping_cues"]
    assert not overlap
