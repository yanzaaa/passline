from dataclasses import dataclass
import unicodedata
from passline.models.subtitle import SubtitleCue, SubtitleFile
from passline.qc.thresholds import (
    CPS_VIOLATION, CPS_VIOLATION_CJK,
    LINE_CHAR_MAX, LINE_CHAR_MAX_CJK,
    MIN_DURATION_MS, MAX_LINES_PER_CUE
)

@dataclass(frozen=True)
class TranscriptSegment:
    """One time-aligned unit from the transcription API."""
    word: str
    start_s: float
    end_s: float

def _display_width(text: str) -> int:
    """Return the display column count of *text* using East Asian width."""
    total = 0
    for ch in text:
        w = unicodedata.east_asian_width(ch)
        total += 2 if w in ("W", "F") else 1
    return total

def build_cues(
    segments: list[TranscriptSegment],
    language: str = "und",
    max_cps: float | None = None,
    max_line_chars: int | None = None,
    max_display_cols: int | None = None,
    min_duration_ms: int | None = None,
) -> SubtitleFile:
    """Assemble a SubtitleFile from time-aligned transcript segments."""
    is_cjk = language.lower() in {"zh", "ja", "ko", "zh-cn", "zh-tw", "zh-hant", "zh-hans"}
    cps_limit = max_cps or (CPS_VIOLATION_CJK if is_cjk else CPS_VIOLATION)
    line_limit = max_line_chars or (LINE_CHAR_MAX_CJK if is_cjk else LINE_CHAR_MAX)
    if max_display_cols is not None:
        line_limit = max_display_cols
    dur_min_ms = min_duration_ms or MIN_DURATION_MS

    raw_cues = []
    
    current_cue_lines = []
    current_cue_segments = []
    current_line = ""
    current_line_segments = []
    cue_start_s = None
    current_end_s = None

    def close_cue(lines: list[str], line: str, line_segs: list[TranscriptSegment], cue_segs: list[TranscriptSegment], start_s: float, end_s: float, next_start_s: float | None = None):
        final_lines = list(lines)
        if line:
            final_lines.append(line)
        if not final_lines:
            return
            
        final_segments = list(cue_segs)
        final_segments.extend(line_segs)
            
        end_ms = int(end_s * 1000)
        start_ms = int(start_s * 1000)
        
        if end_ms - start_ms < dur_min_ms:
            end_ms = start_ms + dur_min_ms
            if next_start_s is not None:
                next_start_ms = int(next_start_s * 1000)
                end_ms = min(end_ms, next_start_ms - 1)
        
        raw_cues.append({
            "start_ms": start_ms,
            "end_ms": end_ms,
            "lines": final_lines,
            "segments": final_segments,
        })

    for segment in segments:
        word = segment.word.strip()
        if not word:
            continue

        if cue_start_s is None:
            cue_start_s = segment.start_s
            current_end_s = segment.end_s
            current_line = word
            current_line_segments = [segment]
            current_cue_segments = []
            continue
            
        # Do not merge segments that are more than 1 second apart into the same cue.
        if segment.start_s - current_end_s > 1.0:
            close_cue(current_cue_lines, current_line, current_line_segments, current_cue_segments, cue_start_s, current_end_s, segment.start_s)
            current_cue_lines = []
            current_cue_segments = []
            current_line = word
            current_line_segments = [segment]
            cue_start_s = segment.start_s
            current_end_s = segment.end_s
            continue

        candidate = current_line + (" " if current_line and not is_cjk else "") + word
        candidate_width = _display_width(candidate) if is_cjk else len(candidate)

        if candidate_width <= line_limit:
            current_line = candidate
            current_line_segments.append(segment)
            current_end_s = segment.end_s
        elif len(current_cue_lines) < MAX_LINES_PER_CUE - 1:
            current_cue_lines.append(current_line)
            current_cue_segments.extend(current_line_segments)
            current_line = word
            current_line_segments = [segment]
            current_end_s = segment.end_s
        else:
            close_cue(current_cue_lines, current_line, current_line_segments, current_cue_segments, cue_start_s, current_end_s, segment.start_s)
            current_cue_lines = []
            current_cue_segments = []
            current_line = word
            current_line_segments = [segment]
            cue_start_s = segment.start_s
            current_end_s = segment.end_s

    if cue_start_s is not None:
        close_cue(current_cue_lines, current_line, current_line_segments, current_cue_segments, cue_start_s, current_end_s)

    # Step 5: Overlap prevention
    for i in range(len(raw_cues) - 1):
        if raw_cues[i]["end_ms"] > raw_cues[i+1]["start_ms"]:
            raw_cues[i]["end_ms"] = raw_cues[i+1]["start_ms"] - 1

    # Step 6: CPS enforcement (reflow)
    final_cues = []
    cue_index = 1
    anomalies = []

    def pack_segments(segs: list[TranscriptSegment]) -> list[str]:
        packed_lines = []
        curr = ""
        for s in segs:
            w = s.word.strip()
            if not w: continue
            cand = curr + (" " if curr and not is_cjk else "") + w
            cand_w = _display_width(cand) if is_cjk else len(cand)
            if cand_w <= line_limit:
                curr = cand
            else:
                if curr:
                    packed_lines.append(curr)
                curr = w
        if curr:
            packed_lines.append(curr)
        return packed_lines

    def process_cue(start_ms: int, end_ms: int, segs: list[TranscriptSegment]):
        nonlocal cue_index
        lines = pack_segments(segs)
        total_chars = sum(_display_width(ln) if is_cjk else len(ln) for ln in lines)
        dur = end_ms - start_ms
        cps = (total_chars / dur * 1000) if dur > 0 else float('inf')
        
        if cps > cps_limit and len(segs) > 1:
            mid = len(segs) // 2
            
            # Find a split index that satisfies dur_min_ms for both halves
            best_split = -1
            best_diff = float('inf')
            
            for i in range(1, len(segs)):
                left_start = start_ms
                left_end = int(segs[i-1].end_s * 1000)
                right_start = int(segs[i].start_s * 1000)
                right_end = end_ms
                
                if left_end < right_start:
                    left_end = right_start - 1
                elif left_end >= right_start:
                    left_end = right_start - 1
                    
                left_dur = left_end - left_start
                right_dur = right_end - right_start
                
                if left_dur >= dur_min_ms and right_dur >= dur_min_ms:
                    lines1 = pack_segments(segs[:i])
                    lines2 = pack_segments(segs[i:])
                    if len(lines1) <= MAX_LINES_PER_CUE and len(lines2) <= MAX_LINES_PER_CUE:
                        diff = abs(i - mid)
                        if diff < best_diff:
                            best_diff = diff
                            best_split = i
            
            if best_split != -1:
                i = best_split
                left_start = start_ms
                right_start = int(segs[i].start_s * 1000)
                left_end = right_start - 1
                right_end = end_ms
                
                process_cue(left_start, left_end, segs[:i])
                process_cue(right_start, right_end, segs[i:])
                return
                
            # Fallback to strict midpoint split if segment boundary split wasn't possible
            mid_s = start_ms + (dur // 2)
            if (mid_s - start_ms) >= dur_min_ms and (end_ms - mid_s) >= dur_min_ms:
                lines1 = pack_segments(segs[:mid])
                lines2 = pack_segments(segs[mid:])
                if len(lines1) <= MAX_LINES_PER_CUE and len(lines2) <= MAX_LINES_PER_CUE:
                    process_cue(start_ms, mid_s - 1, segs[:mid])
                    process_cue(mid_s, end_ms, segs[mid:])
                    return
                        
        c = SubtitleCue(index=cue_index, start_ms=start_ms, end_ms=end_ms, lines=lines)
        c_cps = c.cps_display if is_cjk else c.cps
        if c_cps > cps_limit:
            anomalies.append(f"Cue {c.index}: CPS {c_cps:.2f} exceeds limit {cps_limit} after reflow")
        final_cues.append(c)
        cue_index += 1

    for rc in raw_cues:
        process_cue(rc["start_ms"], rc["end_ms"], rc["segments"])

    return SubtitleFile(
        cues=tuple(final_cues),
        language=language,
        parse_anomalies=tuple(anomalies)
    )
