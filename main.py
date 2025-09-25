from __future__ import annotations

import os
import re
from pathlib import Path
import json
import mimetypes
from typing import List
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response
from fastapi import Body
from fastapi.staticfiles import StaticFiles


APP_TITLE = "ASRKH10k Dataset"
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
METADATA_PATH = UPLOAD_DIR / "metadata.json"
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus", ".wma", ".aiff"}

app = FastAPI(title=APP_TITLE)
app.mount("/static", StaticFiles(directory="static"), name="static")


def _human_size(num_bytes: int) -> str:
    step = 1024.0
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < step or unit == "TB":
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes/step:.2f} {unit}"
        num_bytes /= step


def _safe_filename(name: str) -> str:
    base = os.path.basename(name).strip().replace("\x00", "")
    # Keep letters, numbers, dot, dash, underscore; replace others with underscore
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    # Prevent empty names
    if not base or base in {".", ".."}:
        base = "file"
    # Truncate to a reasonable length
    if len(base) > 200:
        root, ext = os.path.splitext(base)
        base = root[:180] + ext[:20]
    return base


def _unique_path(target: Path) -> Path:
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    parent = target.parent
    i = 1
    while True:
        candidate = parent / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def list_files() -> list[dict]:
    # Load metadata (labels, verified, lang, gender)
    metadata: dict[str, dict] = {}
    if METADATA_PATH.exists():
        try:
            metadata = json.loads(METADATA_PATH.read_text())
        except Exception:
            metadata = {}
    dirty = False
    items: list[dict] = []
    for p in sorted(UPLOAD_DIR.glob("*")):
        if not p.is_file():
            continue
        if p.name == METADATA_PATH.name:
            continue
        if p.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        stat = p.stat()
        mtime = stat.st_mtime
        size_h = _human_size(stat.st_size)
        mtime_iso = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        meta_val = metadata.get(p.name)
        label = ""
        verified = False
        lang = "Khmer"
        gender = "Male"
        if isinstance(meta_val, dict):
            # ensure defaults
            if "label" not in meta_val:
                meta_val["label"] = ""
                dirty = True
            if "verified" not in meta_val:
                meta_val["verified"] = False
                dirty = True
            if "lang" not in meta_val:
                meta_val["lang"] = "Khmer"
                dirty = True
            if "gender" not in meta_val:
                meta_val["gender"] = "Male"
                dirty = True
            if "speaker" not in meta_val:
                meta_val["speaker"] = ""
                dirty = True
            label = str(meta_val.get("label") or "")
            verified = bool(meta_val.get("verified") or False)
            lang = str(meta_val.get("lang") or "Khmer")
            gender = str(meta_val.get("gender") or "Male")
            speaker = str(meta_val.get("speaker") or "")
            # Keep size/date in metadata as well
            if meta_val.get("size_h") != size_h:
                meta_val["size_h"] = size_h
                dirty = True
            if meta_val.get("size_bytes") != stat.st_size:
                meta_val["size_bytes"] = stat.st_size
                dirty = True
            if meta_val.get("mtime_iso") != mtime_iso:
                meta_val["mtime_iso"] = mtime_iso
                dirty = True
            # normalize back
            metadata[p.name] = {
                "label": label,
                "verified": verified,
                "lang": lang,
                "gender": gender,
                "speaker": speaker,
                "size_h": meta_val.get("size_h", size_h),
                "size_bytes": meta_val.get("size_bytes", stat.st_size),
                "mtime_iso": meta_val.get("mtime_iso", mtime_iso),
            }
        elif isinstance(meta_val, str):
            label = meta_val
            metadata[p.name] = {
                "label": label,
                "verified": False,
                "lang": "Khmer",
                "gender": "Male",
                "speaker": "",
                "size_h": size_h,
                "size_bytes": stat.st_size,
                "mtime_iso": mtime_iso,
            }
            dirty = True
        else:
            metadata[p.name] = {
                "label": "",
                "verified": False,
                "lang": "Khmer",
                "gender": "Male",
                "speaker": "",
                "size_h": size_h,
                "size_bytes": stat.st_size,
                "mtime_iso": mtime_iso,
            }
            dirty = True
        items.append({
            "name": p.name,
            "size": stat.st_size,
            "size_h": size_h,
            "mtime": mtime,
            "mtime_iso": mtime_iso,
            "label": label,
            "verified": verified,
            "lang": lang,
            "gender": gender,
            "speaker": speaker if 'speaker' in locals() else "",
        })
    # Default: most recent first
    items.sort(key=lambda x: x["mtime"], reverse=True)
    # Write back defaults if needed
    if dirty:
        try:
            METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
        except Exception:
            pass
    return items


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    files = list_files()
    rows = []
    for f in files:
        display_label = f["label"] if f["label"] else "None"
        verified = f.get("verified", False)
        v_text = "Verified" if verified else "Verify"
        v_state = "true" if verified else "false"
        # compute select attrs
        lang = f.get("lang", "Khmer")
        kh_sel = " selected" if lang == "Khmer" else ""
        en_sel = " selected" if lang == "English" else ""
        mix_sel = " selected" if lang == "Mix-Both" else ""
        gender = f.get("gender", "Male")
        male_sel = " selected" if gender == "Male" else ""
        female_sel = " selected" if gender == "Female" else ""
        row = f"""
        <tr class=\"file-row\" data-name=\"{f['name']}\" data-size=\"{f['size']}\" data-time=\"{int(f['mtime'])}\" data-verified=\"{v_state}\">
            <td class=\"name\">
              <a class=\"file-link\" href=\"#\" data-filename=\"{f['name']}\">{f['name']}</a>
              <span class=\"eq\" aria-hidden=\"true\"><i></i><i></i><i></i></span>
            </td>
            <td class=\"down\"><a class=\"btn btn-download btn-small\" href=\"/download/{f['name']}\" download title=\"Download\" aria-label=\"Download\">⬇</a></td>
            <td class=\"size\">{f['size_h']}</td>
            <td class=\"date\">{f['mtime_iso']}</td>
            <td class=\"label\"><span class=\"label-text\" data-filename=\"{f['name']}\">{display_label}</span></td>
            <td class=\"speaker\"><span class=\"speaker-text\" data-filename=\"{f['name']}\">{(f.get('speaker') or '') or 'None'}</span> <button class=\"btn btn-icon btn-speaker\" title=\"Pick speaker\" aria-label=\"Pick speaker\">▾</button></td>
            <td class=\"lang\"><select class=\"lang-select\" data-filename=\"{f['name']}\">
              <option value=\"Khmer\"{kh_sel}>Khmer</option>
              <option value=\"English\"{en_sel}>English</option>
              <option value=\"Mix-Both\"{mix_sel}>Mix-Both</option>
            </select></td>
            <td class=\"gender\"><select class=\"gender-select\" data-filename=\"{f['name']}\">
              <option value=\"Male\"{male_sel}>Male</option>
              <option value=\"Female\"{female_sel}>Female</option>
            </select></td>
            <td class=\"verify\"><button class=\"btn btn-verify\" data-filename=\"{f['name']}\" data-verified=\"{v_state}\">{v_text}</button></td>
        </tr>
        """
        rows.append(row)

    table_rows = "\n".join(rows) if rows else """
        <tr><td colspan=\"9\" class=\"empty\">No files uploaded yet.</td></tr>
    """

    return f"""
<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{APP_TITLE}</title>
  <link rel=\"icon\" type=\"image/png\" href=\"/static/chlat.png\" />
  <style>
    :root {{
      --bg: #0f172a;        /* slate-900 */
      --panel: #111827;     /* gray-900 */
      --panel-2: #0b1220;   /* darker */
      --text: #e5e7eb;      /* gray-200 */
      --muted: #9ca3af;     /* gray-400 */
      --primary: #22d3ee;   /* cyan-400 */
      --accent: #8b5cf6;    /* violet-500 */
      --ok: #10b981;        /* emerald-500 */
      --warn: #f59e0b;      /* amber-500 */
      --danger: #ef4444;    /* red-500 */
      --border: #1f2937;    /* gray-800 */
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ height: 100%; }}
    body {{ margin: 0; font-family: system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, Noto Sans, Helvetica, Arial, \"Apple Color Emoji\", \"Segoe UI Emoji\"; background: linear-gradient(180deg, var(--bg), var(--panel-2)); color: var(--text); }}
    header {{ padding: 24px 16px 8px; text-align: center; }}
    header h1 {{ margin: 0; font-size: 24px; letter-spacing: 0.4px; display:inline-flex; align-items:center; gap:10px; }}
    header p {{ margin: 6px 0 0; color: var(--muted); }}
    .logo {{ width:40px; height:40px; border-radius:8px; object-fit:contain; background: transparent; display:inline-block; }}

    .container {{ max-width: 1400px; margin: 0 auto; padding: 16px; }}

    .card {{ background: rgba(17,24,39,0.8); border: 1px solid var(--border); border-radius: 12px; padding: 16px; box-shadow: 0 6px 24px rgba(0,0,0,0.3); width: 100%; max-width: 1280px; }}
    .row {{ display: grid; grid-template-columns: 1fr; gap: 16px; justify-items: center; }}
    @media (max-width: 900px) {{ .row {{ grid-template-columns: 1fr; }} }}

    /* Upload */
    .upload {{ display: flex; align-items: center; gap: 12px; background: linear-gradient(135deg, rgba(34,211,238,0.08), rgba(139,92,246,0.08)); border: 1px dashed rgba(34,211,238,0.35); padding: 16px; border-radius: 10px; }}
    .upload input[type=file] {{ flex: 1; padding: 10px; color: var(--text); background: #0b1220; border: 1px solid var(--border); border-radius: 8px; }}
    .upload button {{ padding: 10px 14px; border: 0; border-radius: 8px; background: linear-gradient(135deg, var(--primary), var(--accent)); color: #04121a; font-weight: 700; cursor: pointer; transition: transform .05s ease; }}
    .upload button:hover {{ transform: translateY(-1px); }}

    /* Controls */
    .controls {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 14px; }}
    @media (max-width: 900px) {{ .controls {{ grid-template-columns: 1fr; }} }}
    .control label {{ display: block; font-size: 12px; color: var(--muted); margin-bottom: 6px; }}
    .control input, .control select {{ width: 100%; background: #0b1220; color: var(--text); border: 1px solid var(--border); border-radius: 8px; padding: 8px; }}
    .lang-select, .gender-select {{ background: #0b1220; color: var(--text); border: 1px solid var(--border); border-radius: 8px; padding: 6px; }}

    /* Table */
    .table-wrap {{ overflow: auto; border: 1px solid var(--border); border-radius: 10px; margin-top: 12px; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 1000px; }}
    th, td {{ padding: 12px 14px; border-bottom: 1px solid var(--border); }}
    thead th {{ position: sticky; top: 0; background: #0b1220; color: var(--muted); text-align: left; font-weight: 600; font-size: 13px; }}
    tbody tr:hover {{ background: rgba(34,211,238,0.06); }}
    td.name a {{ color: var(--primary); text-decoration: none; }}
    td.name a:hover {{ text-decoration: underline; }}
    td.empty {{ text-align: center; color: var(--muted); padding: 28px; }}

    /* Search bar */
    .search-bar {{ margin-top: 14px; background: rgba(11,18,32,0.92); border: 1px solid var(--border); border-radius: 10px; backdrop-filter: blur(6px); padding: 12px; display: flex; gap: 10px; align-items: center; }}
    .search-bar input {{ flex: 1; background: #0b1220; color: var(--text); border: 1px solid var(--border); border-radius: 8px; padding: 10px; }}
    .label-text {{ cursor: text; padding: 2px 6px; border-radius: 6px; }}
    .label-text:hover {{ background: rgba(139,92,246,0.15); }}
    .label-input {{ width: 100%; background: #0b1220; color: var(--text); border: 1px solid var(--border); border-radius: 6px; padding: 6px; }}
    .btn {{ font: inherit; padding: 6px 10px; border-radius: 8px; border: 1px solid var(--border); background: #0b1220; color: var(--text); cursor: pointer; }}
    .btn-verify[data-verified=\"true\"] {{ background: rgba(16,185,129,0.15); border-color: rgba(16,185,129,0.5); color: #10b981; }}
    .btn-verify[data-verified=\"false\"] {{ background: rgba(139,92,246,0.15); border-color: rgba(139,92,246,0.5); color: #8b5cf6; }}
    .btn-download {{ background: rgba(34,211,238,0.15); border-color: rgba(34,211,238,0.5); color: #22d3ee; text-decoration: none; display: inline-block; }}
    .btn-small {{ padding: 2px 6px; font-size: 12px; }}
    .btn-icon {{ padding: 2px 6px; font-size: 12px; background: rgba(139,92,246,0.15); border-color: rgba(139,92,246,0.5); color: #8b5cf6; }}
    .eq {{ display: none; margin-left: 8px; vertical-align: middle; }}
    .name.playing .eq {{ display: inline-flex; gap: 2px; }}
    .eq i {{ display: inline-block; width: 3px; height: 10px; background: var(--primary); animation: bounce 0.8s infinite ease-in-out; }}
    .eq i:nth-child(2) {{ animation-delay: 0.1s; }}
    .eq i:nth-child(3) {{ animation-delay: 0.2s; }}
    @keyframes bounce {{
      0%, 100% {{ transform: scaleY(0.4); opacity: 0.6; }}
      50% {{ transform: scaleY(1); opacity: 1; }}
    }}
    .pagination-bar {{ margin-top: 10px; display: flex; align-items: center; gap: 10px; color: var(--muted); justify-content: center; }}
    .pagination-bar .btn {{ padding: 6px 10px; }}
    .badge {{ display: inline-block; background: rgba(34,211,238,0.1); color: var(--primary); border: 1px solid rgba(34,211,238,0.3); font-size: 12px; padding: 2px 8px; border-radius: 999px; }}
    footer {{ text-align: center; color: var(--muted); padding: 16px 0; font-size: 12px; }}
  </style>
</head>
<body>
  <header>
    <h1><img class=\"logo\" src=\"/static/chlat.png\" alt=\"logo\" />{APP_TITLE}</h1>
    <p>"Data is the foundation of Deep Learning, no data no Deep Learning"</p>
  </header>
  <div class=\"container\">
    <div class=\"row\">
      <section class=\"card\">
        <form class=\"upload\" action=\"/upload\" method=\"post\" enctype=\"multipart/form-data\">
          <input type=\"file\" name=\"files\" id=\"file\" accept=\"audio/*\" multiple required />
          <button type=\"submit\">Upload</button>
        </form>

        <div class=\"controls\">
          <div class=\"control\">
            <label for=\"sort_date\">Sort</label>
            <select id=\"sort_date\">
              <option value=\"date_desc\" selected>Newest</option>
              <option value=\"date_asc\">Oldest</option>
            </select>
          </div>
          <div class=\"control\">
            <label for=\"sort_size\">Size Sort</label>
            <select id=\"sort_size\">
              <option value=\"none\" selected>None</option>
              <option value=\"size_desc\">Large → Small</option>
              <option value=\"size_asc\">Small → Large</option>
            </select>
          </div>
          <div class=\"control\">
            <label for=\"sort_name\">Name Sort</label>
            <select id=\"sort_name\">
              <option value=\"none\" selected>None</option>
              <option value=\"name_asc\">A → Z</option>
              <option value=\"name_desc\">Z → A</option>
            </select>
          </div>
          
        </div>

        <div class=\"search-bar\">
          <span style=\"opacity:.8\">Search:</span>
          <input id=\"search_input\" type=\"search\" placeholder=\"Type to search files...\" />
        </div>

        <div class=\"table-wrap\">
          <table id=\"files_table\">
            <thead>
              <tr>
                <th>Name</th>
                <th>Down</th>
                <th>Size</th>
                <th>Date</th>
                <th>Label</th>
                <th>Speaker</th>
                <th>Language</th>
                <th>Gender</th>
                <th>Verify</th>
              </tr>
            </thead>
            <tbody id=\"files_tbody\">
              {table_rows}
            </tbody>
          </table>
        <div class=\"pagination-bar\">
          <label for=\"page_size\">Per page</label>
          <select id=\"page_size\">
            <option value=\"20\" selected>20</option>
            <option value=\"40\">40</option>
            <option value=\"60\">60</option>
          </select>
          <button type=\"button\" class=\"btn\" id=\"prev_page\">Prev</button>
          <button type=\"button\" class=\"btn\" id=\"next_page\">Next</button>
          <span id=\"page_info\"></span>
        </div>
      </section>
    </div>
    <footer>
      <small>Tip: Use the search above to quickly filter by name.</small>
    </footer>
  </div>

  <script>
    const $ = (s, root=document) => root.querySelector(s);
    const $$ = (s, root=document) => Array.from(root.querySelectorAll(s));

    const tbody = $('#files_tbody');
    const sortDate = $('#sort_date');
    const sortSize = $('#sort_size');
    const sortName = $('#sort_name');
    const searchInput = $('#search_input');
    const pageSizeSel = $('#page_size');
    const prevBtn = $('#prev_page');
    const nextBtn = $('#next_page');
    const pageInfo = $('#page_info');
    const audio = new Audio();
    let currentPlayingRow = null;

    function getRows() {{ return $$('.file-row', tbody); }}

    function matchesFilters(row) {{
      const name = row.dataset.name.toLowerCase();
      const bs = searchInput.value.trim().toLowerCase();
      if (bs && !name.includes(bs)) return false;
      return true;
    }}

    function sortRows(rows) {{
      // Determine which sort to apply based on dropdowns
      const vDate = sortDate ? sortDate.value : 'date_desc';
      const vSize = sortSize ? sortSize.value : 'none';
      const vName = sortName ? sortName.value : 'none';
      let mode = 'date_desc';
      if (vDate && vDate !== 'none') mode = vDate;
      else if (vSize && vSize !== 'none') mode = vSize;
      else if (vName && vName !== 'none') mode = vName;
      const cmp = (a, b) => {{
        const an = a.dataset.name.toLowerCase();
        const bn = b.dataset.name.toLowerCase();
        const asz = Number(a.dataset.size);
        const bsz = Number(b.dataset.size);
        const at = Number(a.dataset.time);
        const bt = Number(b.dataset.time);
        switch (mode) {{
          case 'date_asc': return at - bt;
          case 'name_asc': return an.localeCompare(bn);
          case 'name_desc': return bn.localeCompare(an);
          case 'size_asc': return asz - bsz;
          case 'size_desc': return bsz - asz;
          case 'date_desc':
          default: return bt - at;
        }}
      }};
      rows.sort(cmp);
    }}

    let currentPage = 1;
    function renderPage(rows) {{
      const ps = Number(pageSizeSel ? pageSizeSel.value : 20) || 20;
      const total = rows.length;
      const pages = Math.max(1, Math.ceil(total / ps));
      if (currentPage > pages) currentPage = pages;
      const start = (currentPage - 1) * ps;
      const end = start + ps;
      rows.forEach((r, i) => {{ r.style.display = (i >= start && i < end) ? '' : 'none'; }});
      if (pageInfo) pageInfo.textContent = `Page ${{currentPage}} of ${{pages}} (${{total}} files)`;
      if (prevBtn) prevBtn.disabled = currentPage <= 1;
      if (nextBtn) nextBtn.disabled = currentPage >= pages;
    }}

    function apply() {{
      const all = getRows();
      const filtered = all.filter(matchesFilters);
      sortRows(filtered);
      // Rebuild tbody in sorted and filtered order
      const frag = document.createDocumentFragment();
      filtered.forEach(r => frag.appendChild(r));
      tbody.appendChild(frag);
      renderPage(filtered);
    }}

    // Toggle verify button
    tbody.addEventListener('click', (e) => {{
      const btn = e.target.closest('.btn-verify');
      if (!btn) return;
      const filename = btn.dataset.filename;
      const current = btn.getAttribute('data-verified') === 'true';
      const next = !current;
      fetch('/verify', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ filename, verified: next }})
      }})
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(data => {{
        const state = data && data.verified ? 'true' : 'false';
        btn.setAttribute('data-verified', state);
        btn.textContent = (state === 'true') ? 'Verified' : 'Verify';
      }})
      .catch(() => {{ /* ignore */ }});
    }});

    // Language dropdown change
    tbody.addEventListener('change', (e) => {{
      const langSel = e.target.closest('.lang-select');
      if (langSel) {{
        const filename = langSel.dataset.filename;
        const lang = langSel.value;
        fetch('/lang', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ filename, lang }})
        }}).catch(() => {{}});
        return;
      }}
      const genderSel = e.target.closest('.gender-select');
      if (genderSel) {{
        const filename = genderSel.dataset.filename;
        const gender = genderSel.value;
        fetch('/gender', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ filename, gender }})
        }}).catch(() => {{}});
        return;
      }}
    }});

    // Speaker dropdown picker
    tbody.addEventListener('click', (e) => {{
      const btn = e.target.closest('.btn-speaker');
      if (!btn) return;
      const td = btn.closest('td');
      const span = td.querySelector('.speaker-text');
      const filename = span.dataset.filename;
      // Gather existing speakers from table
      const options = Array.from(document.querySelectorAll('.speaker-text'))
        .map(x => x.textContent.trim())
        .filter(v => v && v.toLowerCase() !== 'none');
      const uniq = Array.from(new Set(options));
      const sel = document.createElement('select');
      sel.className = 'label-input';
      const noneOpt = document.createElement('option');
      noneOpt.value = '';
      noneOpt.textContent = 'None';
      sel.appendChild(noneOpt);
      uniq.forEach(v => {{ const o = document.createElement('option'); o.value = v; o.textContent = v; sel.appendChild(o); }});
      td.insertBefore(sel, btn);
      sel.addEventListener('change', () => {{
        const value = sel.value.trim();
        fetch('/speaker', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ filename, speaker: value }})
        }})
        .then(r => r.ok ? r.json() : Promise.reject())
        .then(data => {{ span.textContent = (data && data.speaker) || 'None'; }})
        .finally(() => sel.remove());
      }});
      sel.focus();
    }});

    // Click file name to play/pause
    tbody.addEventListener('click', (e) => {{
      const link = e.target.closest('.file-link');
      if (!link) return;
      e.preventDefault();
      const row = link.closest('tr');
      const nameCell = row.querySelector('.name');
      const filename = link.dataset.filename;
      const src = `/stream/${{encodeURIComponent(filename)}}`;
      const isSame = audio.src.endsWith(encodeURIComponent(filename));
      if (isSame && !audio.paused) {{
        audio.pause();
        nameCell.classList.remove('playing');
        return;
      }}
      if (currentPlayingRow) currentPlayingRow.querySelector('.name').classList.remove('playing');
      audio.src = src;
      audio.play().then(() => {{
        nameCell.classList.add('playing');
        currentPlayingRow = row;
      }}).catch(() => {{}});
    }});

    // Inline edit: double-click label to edit and save
    tbody.addEventListener('dblclick', (e) => {{
      // label editing
      const lspan = e.target.closest('.label-text');
      if (lspan) {{
        const td = lspan.parentElement;
        const filename = lspan.dataset.filename;
        const current = lspan.textContent === 'None' ? '' : lspan.textContent;
        const input = document.createElement('input');
        input.type = 'text';
        input.value = current;
        input.className = 'label-input';
        input.maxLength = 200;
        td.replaceChild(input, lspan);
        input.focus();
        input.select();

        const restore = (text) => {{
          const s = document.createElement('span');
          s.className = 'label-text';
          s.dataset.filename = filename;
          s.textContent = text || 'None';
          td.replaceChild(s, input);
        }};

        const commit = () => {{
          const value = input.value.trim();
          fetch('/label', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ filename, label: value }})
          }})
          .then(r => r.ok ? r.json() : Promise.reject())
          .then(data => restore((data && data.label) || 'None'))
          .catch(() => restore(current));
        }};

        input.addEventListener('keydown', (ev) => {{
          if (ev.key === 'Enter') commit();
          if (ev.key === 'Escape') restore(current);
        }});
        input.addEventListener('blur', commit);
        return;
      }}
      // speaker editing
      const sspan = e.target.closest('.speaker-text');
      if (sspan) {{
        const td = sspan.parentElement;
        const filename = sspan.dataset.filename;
        const current = sspan.textContent === 'None' ? '' : sspan.textContent;
        const input = document.createElement('input');
        input.type = 'text';
        input.value = current;
        input.className = 'label-input';
        input.maxLength = 200;
        td.insertBefore(input, sspan);
        td.removeChild(sspan);
        input.focus();
        input.select();
        const restore = (text) => {{
          const s = document.createElement('span');
          s.className = 'speaker-text';
          s.dataset.filename = filename;
          s.textContent = text || 'None';
          td.insertBefore(s, td.firstChild);
          if (input && input.parentElement) input.parentElement.removeChild(input);
        }};
        const commit = () => {{
          const value = input.value.trim();
          fetch('/speaker', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ filename, speaker: value }})
          }})
          .then(r => r.ok ? r.json() : Promise.reject())
          .then(data => restore((data && data.speaker) || 'None'))
          .catch(() => restore(current));
        }};
        input.addEventListener('keydown', (ev) => {{
          if (ev.key === 'Enter') commit();
          if (ev.key === 'Escape') restore(current);
        }});
        input.addEventListener('blur', commit);
        return;
      }}
    }});

    audio.addEventListener('ended', () => {{
      if (currentPlayingRow) currentPlayingRow.querySelector('.name').classList.remove('playing');
      currentPlayingRow = null;
    }});

    [sortDate, sortSize, sortName, searchInput].forEach(el => {{
      el && el.addEventListener('input', apply);
      el && el.addEventListener('change', apply);
    }});
    if (pageSizeSel) pageSizeSel.addEventListener('change', () => {{ currentPage = 1; apply(); }});
    if (prevBtn) prevBtn.addEventListener('click', () => {{ currentPage = Math.max(1, currentPage - 1); apply(); }});
    if (nextBtn) nextBtn.addEventListener('click', () => {{ currentPage = currentPage + 1; apply(); }});

    // Initial apply to enforce default sort
    apply();
  </script>
</body>
</html>
"""


@app.post("/upload")
async def upload(files: List[UploadFile] = File(...)):
    saved = 0
    # Determine next sequential index (six digits) based on existing files
    existing_nums = []
    for p in UPLOAD_DIR.glob("*"):
        if p.name == METADATA_PATH.name or not p.is_file():
            continue
        stem = p.stem
        if len(stem) == 6 and stem.isdigit():
            try:
                existing_nums.append(int(stem))
            except Exception:
                pass
    next_num = max(existing_nums) + 1 if existing_nums else 1

    for uf in files:
        try:
            raw_name = uf.filename or "file"
            safe = _safe_filename(raw_name)
            # Keep extension, rename to sequential number
            ext = os.path.splitext(safe)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                # skip non-audio
                await uf.read()  # drain
                continue
            # Find next free numbered filename
            while True:
                candidate = UPLOAD_DIR / f"{next_num:06d}{ext}"
                if not candidate.exists():
                    target = candidate
                    next_num += 1
                    break
                next_num += 1
            # Only allow a subset of audio extensions as an extra safety measure
            with target.open("wb") as out:
                content = await uf.read()
                out.write(content)
            saved += 1
            # Update metadata for the new file with defaults and size/date
            data: dict[str, dict] = {}
            if METADATA_PATH.exists():
                try:
                    data = json.loads(METADATA_PATH.read_text())
                except Exception:
                    data = {}
            stat = target.stat()
            mtime_iso = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            data[target.name] = {
                "label": "",
                "verified": False,
                "lang": "Khmer",
                "gender": "Male",
                "size_h": _human_size(stat.st_size),
                "size_bytes": stat.st_size,
                "mtime_iso": mtime_iso,
            }
            try:
                METADATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            except Exception:
                pass
        finally:
            await uf.close()
    # Redirect back home
    resp: Response = RedirectResponse(url="/", status_code=303)
    return resp


@app.get("/download/{filename}")
def download(filename: str):
    safe = _safe_filename(filename)
    path = (UPLOAD_DIR / safe).resolve()
    # Ensure the path is within the upload dir
    try:
        path.relative_to(UPLOAD_DIR.resolve())
    except Exception:
        return Response("Invalid path", status_code=400)
    if not path.exists() or not path.is_file():
        return Response("File not found", status_code=404)
    return FileResponse(path, media_type="application/octet-stream", filename=path.name)


@app.post("/upload_outside")
async def upload_outside(
    file: UploadFile = File(...),
    label: str | None = Form(None),
    language: str = Form("Khmer"),
    gender: str | None = Form(None),
    verified: bool = Form(False),
    speaker: str | None = Form(None),
):
    # Validate language and gender
    lang = language if language in {"Khmer", "English", "Mix-Both"} else "Khmer"
    gen = gender if gender in {"Male", "Female"} else "None"
    spk = speaker or ""

    # Determine next sequential index (six digits)
    existing_nums: list[int] = []
    for p in UPLOAD_DIR.glob("*"):
        if p.name == METADATA_PATH.name or not p.is_file():
            continue
        stem = p.stem
        if len(stem) == 6 and stem.isdigit():
            try:
                existing_nums.append(int(stem))
            except Exception:
                pass
    next_num = max(existing_nums) + 1 if existing_nums else 1

    # Validate extension
    orig_name = file.filename or "file"
    safe = _safe_filename(orig_name)
    ext = os.path.splitext(safe)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        await file.read()  # drain
        return {"ok": False, "error": "Unsupported file type"}

    # Allocate numbered target path
    while True:
        candidate = UPLOAD_DIR / f"{next_num:06d}{ext}"
        if not candidate.exists():
            target = candidate
            next_num += 1
            break
        next_num += 1

    # Save file
    content = await file.read()
    with target.open("wb") as out:
        out.write(content)

    # Update metadata
    data: dict[str, dict] = {}
    if METADATA_PATH.exists():
        try:
            data = json.loads(METADATA_PATH.read_text())
        except Exception:
            data = {}
    stat = target.stat()
    mtime_iso = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    data[target.name] = {
        "label": (label or ""),
        "verified": bool(verified),
        "lang": lang,
        "gender": gen,
        "speaker": spk,
        "size_h": _human_size(stat.st_size),
        "size_bytes": stat.st_size,
        "mtime_iso": mtime_iso,
        "original_name": orig_name,
    }
    try:
        METADATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        pass

    return {
        "ok": True,
        "file": target.name,
        "label": data[target.name]["label"],
        "lang": lang,
        "gender": gen,
        "verified": bool(verified),
        "speaker": spk,
        "size_bytes": stat.st_size,
        "mtime_iso": mtime_iso,
    }


@app.get("/stream/{filename}")
def stream(filename: str):
    safe = _safe_filename(filename)
    path = (UPLOAD_DIR / safe).resolve()
    try:
        path.relative_to(UPLOAD_DIR.resolve())
    except Exception:
        return Response("Invalid path", status_code=400)
    if not path.exists() or not path.is_file():
        return Response("File not found", status_code=404)
    mime, _ = mimetypes.guess_type(path.name)
    media_type = mime or "audio/mpeg"
    # Do not pass filename to allow inline playback (no attachment header)
    return FileResponse(path, media_type=media_type)

@app.post("/label")
async def set_label(payload: dict = Body(...)):
    filename = str(payload.get("filename") or "").strip()
    label = str(payload.get("label") or "").strip()
    safe = _safe_filename(filename)
    path = (UPLOAD_DIR / safe)
    if not path.exists() or not path.is_file():
        return {"ok": False, "error": "File not found"}
    # Sanitize label: remove control chars and limit length
    label = re.sub(r"[\x00-\x1F\x7F]", "", label)[:200]
    # Load, update, save metadata
    data: dict[str, dict] = {}
    if METADATA_PATH.exists():
        try:
            data = json.loads(METADATA_PATH.read_text())
        except Exception:
            data = {}
    entry = data.get(safe)
    if isinstance(entry, dict):
        entry_verified = bool(entry.get("verified") or False)
        entry_lang = str(entry.get("lang") or "Khmer")
        entry_gender = str(entry.get("gender") or "Male")
    elif isinstance(entry, str):
        entry_verified = False
        entry_lang = "Khmer"
        entry_gender = "Male"
    else:
        entry_verified = False
        entry_lang = "Khmer"
        entry_gender = "Male"
    # also refresh size/date fields
    stat = path.stat()
    mtime_iso = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    data[safe] = {
        "label": label,
        "verified": entry_verified,
        "lang": entry_lang,
        "gender": entry_gender,
        "size_h": _human_size(stat.st_size),
        "size_bytes": stat.st_size,
        "mtime_iso": mtime_iso,
    }
    try:
        METADATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        return {"ok": False, "error": "Failed to write metadata"}
    return {"ok": True, "label": label or "None"}


@app.post("/speaker")
async def set_speaker(payload: dict = Body(...)):
    filename = str(payload.get("filename") or "").strip()
    speaker = str(payload.get("speaker") or "").strip()
    safe = _safe_filename(filename)
    path = (UPLOAD_DIR / safe)
    if not path.exists() or not path.is_file():
        return {"ok": False, "error": "File not found"}
    data: dict[str, dict] = {}
    if METADATA_PATH.exists():
        try:
            data = json.loads(METADATA_PATH.read_text())
        except Exception:
            data = {}
    entry = data.get(safe) or {}
    entry_label = str(entry.get("label") or "")
    entry_verified = bool(entry.get("verified") or False)
    entry_lang = str(entry.get("lang") or "Khmer")
    entry_gender = str(entry.get("gender") or "Male")
    stat = path.stat()
    mtime_iso = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    data[safe] = {
        "label": entry_label,
        "verified": entry_verified,
        "lang": entry_lang,
        "gender": entry_gender,
        "speaker": speaker,
        "size_h": _human_size(stat.st_size),
        "size_bytes": stat.st_size,
        "mtime_iso": mtime_iso,
    }
    try:
        METADATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        return {"ok": False, "error": "Failed to write metadata"}
    return {"ok": True, "speaker": speaker or "None"}


@app.post("/verify")
async def set_verified(payload: dict = Body(...)):
    filename = str(payload.get("filename") or "").strip()
    verified = bool(payload.get("verified") or False)
    safe = _safe_filename(filename)
    path = (UPLOAD_DIR / safe)
    if not path.exists() or not path.is_file():
        return {"ok": False, "error": "File not found"}
    data: dict[str, dict] = {}
    if METADATA_PATH.exists():
        try:
            data = json.loads(METADATA_PATH.read_text())
        except Exception:
            data = {}
    entry = data.get(safe)
    if isinstance(entry, dict):
        entry_label = str(entry.get("label") or "")
        entry_lang = str(entry.get("lang") or "Khmer")
        entry_gender = str(entry.get("gender") or "Male")
    elif isinstance(entry, str):
        entry_label = entry
        entry_lang = "Khmer"
        entry_gender = "Male"
    else:
        entry_label = ""
        entry_lang = "Khmer"
        entry_gender = "Male"
    stat = path.stat()
    mtime_iso = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    data[safe] = {
        "label": entry_label,
        "verified": bool(verified),
        "lang": entry_lang,
        "gender": entry_gender,
        "size_h": _human_size(stat.st_size),
        "size_bytes": stat.st_size,
        "mtime_iso": mtime_iso,
    }
    try:
        METADATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        return {"ok": False, "error": "Failed to write metadata"}
    return {"ok": True, "verified": bool(verified)}


@app.post("/lang")
async def set_language(payload: dict = Body(...)):
    filename = str(payload.get("filename") or "").strip()
    lang = str(payload.get("lang") or "Khmer").strip()
    if lang not in {"Khmer", "English", "Mix-Both"}:
        return {"ok": False, "error": "Invalid language"}
    safe = _safe_filename(filename)
    path = (UPLOAD_DIR / safe)
    if not path.exists() or not path.is_file():
        return {"ok": False, "error": "File not found"}
    data: dict[str, dict] = {}
    if METADATA_PATH.exists():
        try:
            data = json.loads(METADATA_PATH.read_text())
        except Exception:
            data = {}
    entry = data.get(safe)
    if isinstance(entry, dict):
        entry_label = str(entry.get("label") or "")
        entry_verified = bool(entry.get("verified") or False)
        entry_gender = str(entry.get("gender") or "Male")
    elif isinstance(entry, str):
        entry_label = entry
        entry_verified = False
        entry_gender = "Male"
    else:
        entry_label = ""
        entry_verified = False
        entry_gender = "Male"
    stat = path.stat()
    mtime_iso = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    data[safe] = {
        "label": entry_label,
        "verified": entry_verified,
        "lang": lang,
        "gender": entry_gender,
        "size_h": _human_size(stat.st_size),
        "size_bytes": stat.st_size,
        "mtime_iso": mtime_iso,
    }


@app.post("/gender")
async def set_gender(payload: dict = Body(...)):
    filename = str(payload.get("filename") or "").strip()
    gender = str(payload.get("gender") or "Male").strip()
    if gender not in {"Male", "Female"}:
        return {"ok": False, "error": "Invalid gender"}
    safe = _safe_filename(filename)
    path = (UPLOAD_DIR / safe)
    if not path.exists() or not path.is_file():
        return {"ok": False, "error": "File not found"}
    data: dict[str, dict] = {}
    if METADATA_PATH.exists():
        try:
            data = json.loads(METADATA_PATH.read_text())
        except Exception:
            data = {}
    entry = data.get(safe)
    if isinstance(entry, dict):
        entry_label = str(entry.get("label") or "")
        entry_verified = bool(entry.get("verified") or False)
        entry_lang = str(entry.get("lang") or "Khmer")
    elif isinstance(entry, str):
        entry_label = entry
        entry_verified = False
        entry_lang = "Khmer"
    else:
        entry_label = ""
        entry_verified = False
        entry_lang = "Khmer"
    stat = path.stat()
    mtime_iso = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    data[safe] = {
        "label": entry_label,
        "verified": entry_verified,
        "lang": entry_lang,
        "gender": gender,
        "size_h": _human_size(stat.st_size),
        "size_bytes": stat.st_size,
        "mtime_iso": mtime_iso,
    }
    try:
        METADATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        return {"ok": False, "error": "Failed to write metadata"}
    return {"ok": True, "gender": gender}
    try:
        METADATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        return {"ok": False, "error": "Failed to write metadata"}
    return {"ok": True, "lang": lang}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=5032, reload=True)
