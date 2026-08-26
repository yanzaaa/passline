import pytest
from passline.io.srt import parse_srt
def test_cp1252_fallback():
    # Use some smart quotes or accents only valid in cp1252 (not utf-8)
    data = b"1\n00:00:01,000 --> 00:00:02,000\nHello \x93world\x94\n"
    sf = parse_srt(data)
    assert sf.srt_dialect.encoding == "cp1252"
    assert "cp1252" in sf.parse_anomalies[0]
    
def test_utf16_rejected():
    data = "1\n00:00:01,000 --> 00:00:02,000\nHello\n".encode("utf-16")
    with pytest.raises(ValueError, match="Null bytes"):
        parse_srt(data)

def test_random_binary_rejected():
    import os
    data = os.urandom(100)
    with pytest.raises(ValueError):
        # Could fail decode entirely or hit the null byte check
        parse_srt(data)
