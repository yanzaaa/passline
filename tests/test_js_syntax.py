import re
import subprocess
from pathlib import Path
import pytest
from passline.dashboard.html import DASHBOARD_HTML

def test_dashboard_js_syntax(tmp_path: Path):
    # Extract JavaScript blocks from the HTML string
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", DASHBOARD_HTML, re.DOTALL | re.IGNORECASE)
    assert scripts, "No script blocks found in dashboard HTML"
    
    js_content = "\n".join(scripts)
    js_file = tmp_path / "dashboard_check.js"
    js_file.write_text(js_content, encoding="utf-8")
    
    # Run node --check
    try:
        result = subprocess.run(["node", "--check", str(js_file)], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        pytest.fail(f"JavaScript syntax error detected by Node:\n{e.stderr}\n{e.stdout}")
    except FileNotFoundError:
        pytest.skip("Node.js is not installed, skipping syntax check")

