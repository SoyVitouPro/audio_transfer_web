from __future__ import annotations

import os
import re
from pathlib import Path
import json
import mimetypes
from typing import List
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response
from fastapi import Body
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


APP_TITLE = "ASRKH10k Dataset"
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
METADATA_PATH = UPLOAD_DIR / "metadata.json"
SPEAKER_META_PATH = UPLOAD_DIR / "speakermeta.json"
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus", ".wma", ".aiff"}

app = FastAPI(title=APP_TITLE)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def _load_speaker_meta() -> list[dict]:
    try:
        if SPEAKER_META_PATH.exists():
            data = json.loads(SPEAKER_META_PATH.read_text())
            if isinstance(data, list):
                meta = []
                for x in data:
                    if isinstance(x, dict):
                        meta.append({
                            "name": str(x.get("name", "")),
                            "gender": str(x.get("gender", "")),
                            "lang": str(x.get("lang", "")),
                        })
                    elif isinstance(x, (str, int)):
                        meta.append({"name": str(x), "gender": "", "lang": ""})
                return meta
    except Exception:
        pass
    return []


def _save_speaker_meta(items: list[dict]) -> None:
    try:
        SPEAKER_META_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2))
    except Exception:
        pass


def _load_speakers() -> list[str]:
    return [m.get("name", "") for m in _load_speaker_meta() if m.get("name")]


def _touch_speaker(name: str) -> None:
    name = (name or "").strip()
    if not name:
        return
    meta = _load_speaker_meta()
    meta = [m for m in meta if m.get("name") != name]
    meta.insert(0, {"name": name, "gender": "", "lang": ""})
    _save_speaker_meta(meta[:100])


def _touch_speaker_with_meta(name: str, gender: str = "", lang: str = "") -> None:
    name = (name or "").strip()
    if not name:
        return
    meta = _load_speaker_meta()
    # remove existing
    meta = [m for m in meta if m.get("name") != name]
    meta.insert(0, {"name": name, "gender": gender, "lang": lang})
    _save_speaker_meta(meta[:100])


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
def home(request: Request):
    files = list_files()
    speakers_list = _load_speakers()
    total_count = len(files)
    total_bytes = sum(f.get("size", 0) for f in files)
    verified_count = sum(1 for f in files if f.get("verified"))
    speakers_set = {(f.get("speaker") or "").strip() for f in files}
    speakers_set.discard("")
    stats_text = f"\" Audio ~ {total_count} records, {len(speakers_set)} speakers, {verified_count} verified, {_human_size(total_bytes)} \""

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "app_title": APP_TITLE,
            "files": files,
            "stats_text": stats_text,
            "speakers_json": json.dumps(speakers_list, ensure_ascii=False),
            "speakers": speakers_list,
        },
    )


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
    if spk:
        _touch_speaker(spk)

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
        entry_speaker = str(entry.get("speaker") or "")
    elif isinstance(entry, str):
        entry_verified = False
        entry_lang = "Khmer"
        entry_gender = "Male"
        entry_speaker = ""
    else:
        entry_verified = False
        entry_lang = "Khmer"
        entry_gender = "Male"
        entry_speaker = ""
    # also refresh size/date fields
    stat = path.stat()
    mtime_iso = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    data[safe] = {
        "label": label,
        "verified": entry_verified,
        "lang": entry_lang,
        "gender": entry_gender,
        "speaker": entry_speaker,
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
    # Touch speaker MRU list
    _touch_speaker(speaker)
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
        entry_speaker = str(entry.get("speaker") or "")
    elif isinstance(entry, str):
        entry_label = entry
        entry_lang = "Khmer"
        entry_gender = "Male"
        entry_speaker = ""
    else:
        entry_label = ""
        entry_lang = "Khmer"
        entry_gender = "Male"
        entry_speaker = ""
    stat = path.stat()
    mtime_iso = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    data[safe] = {
        "label": entry_label,
        "verified": bool(verified),
        "lang": entry_lang,
        "gender": entry_gender,
        "speaker": entry_speaker,
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
        entry_speaker = str(entry.get("speaker") or "")
    elif isinstance(entry, str):
        entry_label = entry
        entry_verified = False
        entry_gender = "Male"
        entry_speaker = ""
    else:
        entry_label = ""
        entry_verified = False
        entry_gender = "Male"
        entry_speaker = ""
    stat = path.stat()
    mtime_iso = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    data[safe] = {
        "label": entry_label,
        "verified": entry_verified,
        "lang": lang,
        "gender": entry_gender,
        "speaker": entry_speaker,
        "size_h": _human_size(stat.st_size),
        "size_bytes": stat.st_size,
        "mtime_iso": mtime_iso,
    }
    try:
        METADATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        return {"ok": False, "error": "Failed to write metadata"}
    return {"ok": True, "lang": lang}


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
        entry_speaker = str(entry.get("speaker") or "")
    elif isinstance(entry, str):
        entry_label = entry
        entry_verified = False
        entry_lang = "Khmer"
        entry_speaker = ""
    else:
        entry_label = ""
        entry_verified = False
        entry_lang = "Khmer"
        entry_speaker = ""
    stat = path.stat()
    mtime_iso = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    data[safe] = {
        "label": entry_label,
        "verified": entry_verified,
        "lang": entry_lang,
        "gender": gender,
        "speaker": entry_speaker,
        "size_h": _human_size(stat.st_size),
        "size_bytes": stat.st_size,
        "mtime_iso": mtime_iso,
    }
    try:
        METADATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        return {"ok": False, "error": "Failed to write metadata"}
    return {"ok": True, "gender": gender}


@app.post("/speaker_add")
async def speaker_add(payload: dict = Body(...)):
    name = str(payload.get("name") or "").strip()
    gender = str(payload.get("gender") or "").strip()
    lang = str(payload.get("lang") or "").strip()
    if not name:
        return {"ok": False, "error": "Missing name"}
    _touch_speaker_with_meta(name, gender, lang)
    return {"ok": True}
    try:
        METADATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        return {"ok": False, "error": "Failed to write metadata"}
    return {"ok": True, "lang": lang}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=5032, reload=True)
