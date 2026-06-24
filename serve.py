"""Pixel dashboard — visualisasi Claude Code session sebagai pixel hewan.

Run:
  python serve.py
  → buka http://localhost:5555

Stack: built-in http.server (no deps), background scanner.
Scan endpoint /api/sessions baca ~/.claude/projects/ live tiap dipanggil.
"""
from __future__ import annotations

import http.server
import json
import re
import socketserver
import sys
import time
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECTS_DIR = Path.home() / ".claude" / "projects"
OPENCLAW_AGENTS_DIR = Path.home() / ".openclaw" / "agents"
PORT = 5555
MAX_OPENCLAW_FILES = 240

CHANNEL_LABELS = {
    "1475686954828828764": "#general",
    "1475852670433755296": "#ctas-pph21",
    "1476063074673885297": "#ctas-unifikasi",
    "1476066241029607565": "#spt-unifikasi",
    "1476096025180770325": "#web-editing",
    "1476134181804179556": "#cuan",
    "1476411242301095936": "#idx-crypto",
    "1476673167782051871": "#monitoring",
    "1476810886751457352": "#tools-ctas",
    "1476844968827027506": "#armbian",
    "1478582467651960933": "#um-pph21",
    "1479205974093856799": "#socmed-strategy",
    "1481041540586668124": "#cuan-armbian",
    "1481999559919013980": "#monitoring-pio",
    "1482246656777781308": "#ctas-faktur",
    "1489034215168147546": "#email-gen",
    "1490920764625387591": "#infra-vm",
    "1492712422723817512": "#gateway",
    "1494609890264748193": "#war",
    "1495929789180153966": "#scam-revenger",
    "1499998037102166106": "#beternak",
    "1500433762310422628": "#video-gen",
    "1504954045482402002": "#vcc",
    "1510009545332752494": "#web3",
    "1510820878676529213": "#trial",
    "1511958823793852456": "#meridian",
}
# Animal palette (emoji yang relatively blocky di sebagian besar font OS)
ANIMALS = [
    "🦊", "🐢", "🐰", "🦉", "🐱", "🐶", "🐭", "🐸",
    "🦝", "🐼", "🐧", "🦦", "🐹", "🐨", "🦘", "🐯",
    "🐺", "🐮", "🐷", "🐵", "🦁", "🐔", "🦆", "🦅",
]




def _clean_user_text_and_label(text: str, current_label: str) -> tuple[str, str]:
    """Extract readable text + channel label from OpenClaw inbound system envelope."""
    label = current_label
    # Examples:
    # System: [.. UTC] Teams DM from Dwi A: message | conversation:{...} | sender:{...}
    m = re.search(r"Teams\s+(DM|Group|Channel)\s+from\s+([^:|]+):\s*(.*)", text, re.I | re.S)
    if m:
        kind = m.group(1).lower()
        name = m.group(2).strip()
        rest = m.group(3).strip()
        if kind == "dm":
            label = f"teams/dm:{name}"
        elif kind == "group":
            label = f"teams/group:{name}"
        else:
            label = f"teams/#{name}"
        text = rest

    # Discord/WhatsApp style injected envelope, e.g.
    # [Discord #general channel id:... Wed ...] wieekun: message
    m = re.match(r"\[(Discord|WhatsApp|Telegram|Signal|Slack)\s+([^\]]+)\]\s+([^:]+):\s*(.*)", text, re.S)
    if m:
        surface = m.group(1).lower()
        target = m.group(2).strip()
        sender = m.group(3).strip()
        rest = m.group(4).strip()
        if surface == "discord":
            channel_name = target.split()[0]
            label = f"discord/{channel_name}"
        else:
            label = f"{surface}/{target.split()[0]}"
        text = f"{sender}: {rest}" if sender else rest

    # Strip appended OpenClaw metadata blobs from readable chat preview.
    for marker in (" | conversation:", " | sender:"):
        idx = text.find(marker)
        if idx >= 0:
            text = text[:idx].rstrip()
    return text, label

def _label_from_session_key(session_key: str, agent_name: str) -> str:
    """Turn OpenClaw sessionKey into a compact dashboard label."""
    if not session_key:
        return f"agent/{agent_name}"
    parts = session_key.split(":")
    if len(parts) >= 4 and parts[0] == "agent":
        channel = parts[2]
        if channel in ("discord", "telegram", "whatsapp", "signal", "slack") and len(parts) >= 5:
            surface = parts[3]
            if surface == "channel" and len(parts) >= 5:
                channel_id = parts[4]
                label = CHANNEL_LABELS.get(channel_id, f"channel:{channel_id[-6:]}")
                return f"{channel}/{label}"
            return f"{channel}/{surface}"
        if channel == "cron" and len(parts) >= 4:
            return f"cron/{parts[3][:8]}"
        if channel == "acp" and len(parts) >= 4:
            return f"acp/{parts[1]}:{parts[3][:8]}"
        return "/".join(parts[1:4])
    return session_key[:28]

def _session_key_from_trajectory(session_file: Path) -> str:
    """Read companion trajectory jsonl for sessionKey when normal session jsonl lacks it."""
    candidates = []
    name = session_file.name
    if name.endswith(".trajectory.jsonl"):
        candidates.append(session_file)
    elif name.endswith(".jsonl"):
        candidates.append(session_file.with_name(session_file.stem + ".trajectory.jsonl"))
    for cand in candidates:
        if not cand.exists():
            continue
        try:
            with open(cand, encoding="utf-8") as fp:
                for line in fp:
                    if not line.strip():
                        continue
                    rec = json.loads(line)
                    key = rec.get("sessionKey") or (rec.get("data") or {}).get("sessionKey")
                    if key:
                        return key
        except Exception:
            pass
    return ""

def _hash_to_animal(session_id: str) -> str:
    """Stable mapping session_id → animal."""
    h = 0
    for ch in session_id:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return ANIMALS[h % len(ANIMALS)]


def _status(age_seconds: float, active_seconds: int = 120) -> str:
    if age_seconds < active_seconds:
        return "active"   # sedang dipakai
    if age_seconds < 300:
        return "recent"   # 5 menit terakhir
    if age_seconds < 3600:
        return "idle"     # 1 jam terakhir
    return "sleeping"


_SCAN_CACHE_BY_WINDOW: dict[int, dict] = {}
_SCAN_TTL = 0.0    # no API cache; frontend polling should reflect latest session log
import threading
_SCAN_LOCK = threading.Lock()

def scan_sessions(active_seconds: int = 120) -> dict:
    """Walk ~/.claude/projects/, kumpulkan info per JSONL session.
    Hasil di-cache 10 detik. Concurrent requests pakai cache existing."""
    now = time.time()
    # Cache hit (data segar)
    cache = _SCAN_CACHE_BY_WINDOW.get(active_seconds)
    if cache and (now - cache["ts"]) < _SCAN_TTL:
        return cache["data"]
    # Cache miss: hanya 1 thread yang boleh scan. Yang lain pakai cache lama.
    if not _SCAN_LOCK.acquire(blocking=False):
        # Thread lain sedang scan. Pakai cache lama (kalau ada).
        cache = _SCAN_CACHE_BY_WINDOW.get(active_seconds)
        if cache is not None:
            return cache["data"]
        # Belum ada cache sama sekali: tunggu lock
        _SCAN_LOCK.acquire()
        try:
            cache = _SCAN_CACHE_BY_WINDOW.get(active_seconds)
            if cache is not None:
                return cache["data"]
        finally:
            _SCAN_LOCK.release()
        # Re-attempt acquire untuk scan ulang
        _SCAN_LOCK.acquire()
    # Lock held, lakukan scan
    out_sessions: list[dict] = []
    if not PROJECTS_DIR.exists() and not OPENCLAW_AGENTS_DIR.exists():
        return {"generated_at": datetime.now(timezone.utc).isoformat(),
                "sessions": [], "error": f"No Claude/OpenClaw sessions found: {PROJECTS_DIR} / {OPENCLAW_AGENTS_DIR}"}

    if OPENCLAW_AGENTS_DIR.exists():
        openclaw_files = []
        for agent_dir in OPENCLAW_AGENTS_DIR.iterdir():
            sess_dir = agent_dir / "sessions"
            if not sess_dir.is_dir():
                continue
            for jsonl in sess_dir.glob("*.jsonl"):
                if ".checkpoint." in jsonl.name or jsonl.name.endswith(".bak"):
                    continue
                try:
                    stat = jsonl.stat()
                except Exception:
                    continue
                openclaw_files.append((stat.st_mtime, agent_dir, jsonl, stat))
        openclaw_files.sort(key=lambda x: x[0], reverse=True)
        for _, agent_dir, jsonl, stat in openclaw_files[:MAX_OPENCLAW_FILES]:
                mtime = stat.st_mtime
                age = max(0.0, now - mtime)
                size_kb = stat.st_size // 1024
                n_messages = 0
                n_tools = 0
                first_user = ""
                last_user = ""
                tool_counts = {}
                last_tool = ""
                model = ""
                session_key = _session_key_from_trajectory(jsonl)
                session_label = _label_from_session_key(session_key, agent_dir.name)
                try:
                    with open(jsonl, encoding="utf-8") as fp:
                        for line in fp:
                            if not line.strip():
                                continue
                            try:
                                rec = json.loads(line)
                            except Exception:
                                continue
                            typ = rec.get("type", "")
                            if typ == "session":
                                session_key = rec.get("sessionKey", "") or session_key
                            if typ == "model_change":
                                model = rec.get("modelId", "") or model
                            msg = rec.get("message") or {}
                            role = msg.get("role", "")
                            if role:
                                n_messages += 1
                            if role == "user":
                                c = msg.get("content", "")
                                user_text = ""
                                if isinstance(c, str):
                                    user_text = c
                                elif isinstance(c, list):
                                    for x in c:
                                        if isinstance(x, dict) and x.get("type") == "text":
                                            user_text = x.get("text") or ""
                                            break
                                if user_text:
                                    user_text, session_label = _clean_user_text_and_label(user_text, session_label)
                                    if not first_user:
                                        first_user = user_text[:80]
                                    last_user = user_text[:120]
                            content = msg.get("content", [])
                            if isinstance(content, list):
                                for c in content:
                                    if not isinstance(c, dict):
                                        continue
                                    if c.get("type") in ("toolCall", "tool_use"):
                                        nm = c.get("name", "")
                                        if nm:
                                            n_tools += 1
                                            tool_counts[nm] = tool_counts.get(nm, 0) + 1
                                            last_tool = nm
                                    elif c.get("type") in ("toolResult", "tool_result"):
                                        nm = c.get("toolName", "")
                                        if nm:
                                            last_tool = nm
                except Exception:
                    pass
                status_now = _status(age, active_seconds)
                expression = "sleeping" if status_now in ("idle", "sleeping") else "awake"
                sid = jsonl.stem.replace(".trajectory", "")
                is_trace = jsonl.stem.endswith(".trajectory")
                out_sessions.append({
                    "id": sid + ("-trace" if is_trace else ""),
                    "short_id": sid[:8],
                    "project": session_label + ("/trace" if is_trace else ""),
                    "n_messages": n_messages,
                    "n_tools": n_tools,
                    "n_subagents": 0,
                    "subagent_types": {},
                    "recent_subagent_types": {},
                    "seconds_since_spawn": None,
                    "last_mod": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
                    "age_seconds": int(age),
                    "status": status_now,
                    "first_user_message": last_user or first_user or session_key or model,
                    "size_kb": size_kb,
                    "tool_top": sorted(tool_counts.items(), key=lambda x: -x[1])[:5],
                    "last_tool": last_tool,
                    "animal": _hash_to_animal(sid + agent_dir.name),
                    "expression": expression,
                })

    if PROJECTS_DIR.exists():
        for proj_dir in PROJECTS_DIR.iterdir():
            if not proj_dir.is_dir():
                continue
            proj_name = proj_dir.name
            for jsonl in proj_dir.glob("*.jsonl"):
                try:
                    stat = jsonl.stat()
                except Exception:
                    continue
                mtime = stat.st_mtime
                age = max(0.0, now - mtime)
                size_kb = stat.st_size // 1024

                n_messages = 0
                n_tools = 0
                n_subagents = 0
                first_user = ""
                tool_counts: dict[str, int] = {}
                last_tool = ""
                recent_subagent_ts = 0.0
                subagent_types: dict[str, int] = {}
                # tid -> {"type": str, "recent": bool, "pending": bool}
                # Per-tid info supaya tidak double-count saat keduanya kondisi
                # terpenuhi (sub-agent BARU spawn yg masih running).
                sub_by_id: dict[str, dict] = {}

                try:
                    with open(jsonl, encoding="utf-8") as fp:
                        for line in fp:
                            n_messages += 1
                            try:
                                rec = json.loads(line)
                            except Exception:
                                continue
                            msg = rec.get("message") or {}
                            role = msg.get("role", "")
                            if role == "user" and not first_user:
                                c = msg.get("content", "")
                                if isinstance(c, str):
                                    if not c.startswith("<"):
                                        first_user = c[:80]
                                elif isinstance(c, list):
                                    for x in c:
                                        if (isinstance(x, dict)
                                                and x.get("type") == "text"):
                                            t = x.get("text", "")
                                            if t and not t.startswith("<"):
                                                first_user = t[:80]
                                                break
                            content = msg.get("content", [])
                            if isinstance(content, list):
                                for c in content:
                                    if not isinstance(c, dict):
                                        continue
                                    ctype = c.get("type")
                                    if ctype == "tool_use":
                                        nm = c.get("name", "")
                                        n_tools += 1
                                        tool_counts[nm] = tool_counts.get(nm, 0) + 1
                                        last_tool = nm
                                        if nm in ("Agent", "Task", "Workflow"):
                                            n_subagents += 1
                                            inp = c.get("input") or {}
                                            if nm == "Workflow":
                                                st = "Workflow"
                                            else:
                                                st = (inp.get("subagent_type")
                                                      or "general")
                                            subagent_types[st] = (
                                                subagent_types.get(st, 0) + 1)
                                            tid = c.get("id", "")
                                            is_recent = False
                                            ts = rec.get("timestamp", "")
                                            if ts:
                                                try:
                                                    from datetime import datetime as _dt
                                                    dt = _dt.fromisoformat(
                                                        ts.replace("Z", "+00:00")
                                                    )
                                                    spawn_ts = dt.timestamp()
                                                    if (now - spawn_ts) < 900:
                                                        is_recent = True
                                                    if spawn_ts > recent_subagent_ts:
                                                        recent_subagent_ts = spawn_ts
                                                except Exception:
                                                    pass
                                            if tid:
                                                sub_by_id[tid] = {
                                                    "type": st,
                                                    "recent": is_recent,
                                                    "pending": True,
                                                }
                                    elif ctype == "tool_result":
                                        tid = c.get("tool_use_id", "")
                                        if tid and tid in sub_by_id:
                                            sub_by_id[tid]["pending"] = False
                except Exception:
                    pass

                # Hitung recent_subagent_types: per-tid SEKALI, qualif=recent OR pending
                recent_subagent_types: dict[str, int] = {}
                for tid, info in sub_by_id.items():
                    if info["recent"] or info["pending"]:
                        st = info["type"]
                        recent_subagent_types[st] = (
                            recent_subagent_types.get(st, 0) + 1)

                # Workflow expand: scan folder transcripts per workflow untuk
                # hitung sub-agent SEBENARNYA (bukan cuma 1 Workflow wrapper).
                # Path: <session_dir>/subagents/workflows/wf_*/agent-*.jsonl
                session_subdir = jsonl.parent / jsonl.stem
                workflows_root = session_subdir / "subagents" / "workflows"
                if workflows_root.exists():
                    # Replace Workflow count → expand jadi sub-agent individu
                    # Bukan dihapus, tapi DITAMBAH supaya represent realita
                    wf_count_old = recent_subagent_types.pop("Workflow", 0)
                    for wf_dir in workflows_root.iterdir():
                        if not wf_dir.is_dir(): continue
                        # Skip workflow yang mtime > 1 jam (sudah selesai lama)
                        wf_mtime = wf_dir.stat().st_mtime
                        if (now - wf_mtime) > 3600: continue
                        # Hitung sub-agent yang ACTIVE (mtime <5 menit + ada pending)
                        for agent_jsonl in wf_dir.glob("agent-*.jsonl"):
                            agent_age = now - agent_jsonl.stat().st_mtime
                            if agent_age > 300: continue   # > 5 menit → completed
                            # Cek meta untuk agent type
                            meta_file = agent_jsonl.with_suffix("")\
                                .with_name(agent_jsonl.stem + ".meta.json")
                            agent_type = "Workflow-child"
                            if meta_file.exists():
                                try:
                                    m = json.loads(meta_file.read_text(
                                        encoding="utf-8"))
                                    agent_type = m.get("agentType",
                                                        "Workflow-child")
                                except Exception:
                                    pass
                            recent_subagent_types[agent_type] = (
                                recent_subagent_types.get(agent_type, 0) + 1)
                            n_subagents += 1
                            subagent_types[agent_type] = (
                                subagent_types.get(agent_type, 0) + 1)

                seconds_since_spawn = (now - recent_subagent_ts
                                        if recent_subagent_ts else None)

                # 3 ekspresi core agent:
                #  - sleeping: idle/sleeping (mtime > 5 menit) → 💤
                #  - hard    : active/recent + ada sub-agent dalam 5 menit → 💪
                #  - awake   : active/recent + bekerja sendiri → 😊
                status_now = _status(age, active_seconds)
                has_active_subagent = bool(recent_subagent_types)
                if status_now in ("idle", "sleeping"):
                    expression = "sleeping"
                elif has_active_subagent:
                    expression = "hard"
                else:
                    expression = "awake"

                session_id = jsonl.stem
                out_sessions.append({
                    "id": session_id,
                    "short_id": session_id[:8],
                    "project": proj_name,
                    "n_messages": n_messages,
                    "n_tools": n_tools,
                    "n_subagents": n_subagents,
                    "subagent_types": subagent_types,
                    "recent_subagent_types": recent_subagent_types,
                    "seconds_since_spawn": seconds_since_spawn,
                    "last_mod": datetime.fromtimestamp(mtime,
                                                        tz=timezone.utc).isoformat(),
                    "age_seconds": int(age),
                    "status": _status(age, active_seconds),
                    "first_user_message": last_user or first_user,
                    "size_kb": size_kb,
                    "tool_top": sorted(tool_counts.items(),
                                        key=lambda x: -x[1])[:5],
                    "last_tool": last_tool,
                    "animal": _hash_to_animal(session_id),
                    "expression": expression,
                })

    # Sort: active first, then by age (newest activity first)
    status_order = {"active": 0, "recent": 1, "idle": 2, "sleeping": 3}
    out_sessions.sort(key=lambda s: (status_order.get(s["status"], 9),
                                       s["age_seconds"]))
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "now": datetime.now(timezone.utc).isoformat(),
        "n_sessions": len(out_sessions),
        "n_active": sum(1 for s in out_sessions if s["status"] == "active"),
        "n_recent": sum(1 for s in out_sessions if s["status"] == "recent"),
        "active_window_seconds": active_seconds,
        "sessions": out_sessions,
        "scanned_limit": MAX_OPENCLAW_FILES if OPENCLAW_AGENTS_DIR.exists() else None,
    }
    _SCAN_CACHE_BY_WINDOW[active_seconds] = {"ts": now, "data": result}
    try:
        _SCAN_LOCK.release()
    except RuntimeError:
        pass
    return result


class Handler(http.server.SimpleHTTPRequestHandler):
    """Serve static files + /api/sessions endpoint."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def log_message(self, fmt, *args):
        # Suppress per-request log noise
        if "/api/" in args[0] if args else False:
            return
        sys.stderr.write(f"  {fmt % args}\n")

    def do_GET(self):
        if self.path.startswith("/api/sessions"):
            try:
                qs = parse_qs(urlparse(self.path).query)
                active_seconds = int((qs.get("active_window") or [120])[0])
                active_seconds = max(30, min(300, active_seconds))
                data = scan_sessions(active_seconds)
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                msg = json.dumps({"error": str(e)}).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)
            return
        return super().do_GET()


def main():
    print(f"🎮 Pixel Dashboard")
    print(f"  Projects dir: {PROJECTS_DIR}")
    print(f"  Server      : http://localhost:{PORT}")
    print(f"  Stop        : Ctrl+C")
    print()
    # Pre-warm cache supaya request pertama dari browser cepat
    print("  Pre-warming scan cache (~20-30s)...")
    pre_t0 = time.time()
    scan_sessions()
    print(f"  Pre-warm selesai dalam {time.time()-pre_t0:.1f}s. Server siap.")
    print()
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    # Bind 0.0.0.0 supaya bisa diakses dari device lain di jaringan lokal
    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), Handler) as srv:
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
