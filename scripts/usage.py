#!/usr/bin/env python3
"""Antigravity (agy) CLI & App 용 AI 남은 사용량 플러그인 스크립트

- Antigravity : OS 보안 저장소(gemini:antigravity) 또는 ~/.gemini/oauth_creds.json 토큰으로
                모델 그룹별(Gemini 5시간 / Claude·GPT 5시간) 남은 쿼터 및 갱신 시각 조회
- Claude      : ~/.claude/.credentials.json (macOS는 키체인) 토큰으로 5시간·주간 사용량 조회
                (~/.claude/ai-usage-cache.json 공유로 429 방지)
- Codex       : ~/.codex/auth.json 실시간 조회 우선, 실패 시 ~/.codex/sessions/**/*.jsonl 로컬 기록 대체
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

HOME = Path.home()
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

MIN_INTERVAL_AGY_MS = 180_000
MIN_INTERVAL_CLAUDE_MS = 180_000
MIN_INTERVAL_CODEX_MS = 120_000

SHARED_CLAUDE = HOME / ".claude" / "ai-usage-cache.json"
SHARED_AGY = HOME / ".gemini" / "agy-usage-cache.json"
PLUGIN_CFG = HOME / ".gemini" / "agy-usage-config.json"

WIDGET_CFG = (
    HOME / "Library" / "Application Support" / "UsageWidget" / "config.json"
    if IS_MAC
    else Path(os.environ.get("APPDATA", str(HOME))) / "UsageWidget" / "config.json"
)

ALL_PROVIDERS = ("Antigravity", "Claude", "Codex")
AGY_LABELS = ("Gemini 5시간", "Claude·GPT 5시간")
SHORT = {"5시간": "5h", "주간": "주", "Gemini 5시간": "Gem", "Claude·GPT 5시간": "Cl·GPT"}
AGY_HEADERS = {"User-Agent": "antigravity"}


# ---------- 공통 HTTP / 오류 처리 ----------
def http_json(url: str, token: str, body: dict | None = None, headers: dict | None = None) -> dict:
    h = {"Authorization": f"Bearer {token}", **(headers or {})}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.load(r)


def err_dict(e: Exception, target: str = "Claude Code·agy") -> dict:
    if isinstance(e, urllib.error.HTTPError):
        if e.code in (401, 403):
            return {"error": f"토큰 만료 - {target} 실행 시 자동 갱신", "short": "만료", "retry": 120_000}
        if e.code == 429:
            try:
                wait = int(e.headers.get("Retry-After") or 0)
            except ValueError:
                wait = 0
            return {
                "error": "요청 제한(429) - 잠시 후 자동 재시도",
                "short": "대기",
                "retry": max(wait * 1000, 300_000),
            }
        return {"error": f"서버 오류 HTTP {e.code}", "short": "오류", "retry": 120_000}
    if isinstance(e, (urllib.error.URLError, TimeoutError, OSError)):
        return {"error": "네트워크 연결 확인", "short": "연결", "retry": 60_000}
    return {"error": str(e)[:60], "short": "오류", "retry": 120_000}


# ---------- 설정 읽기 / 저장 ----------
def load_cfg() -> dict:
    cfg: dict = {}
    for p in (WIDGET_CFG, PLUGIN_CFG):
        try:
            if p.exists():
                cfg.update(json.loads(p.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            pass
    en = [("Antigravity" if n == "Gemini" else n) for n in cfg.get("enabled", [])]
    en = [n for n in ALL_PROVIDERS if n in en]
    # Antigravity 플러그인이므로 기본값에 Antigravity를 포함
    if not en:
        en = ["Antigravity", "Claude", "Codex"]
    cfg["enabled"] = en
    agy_items = [l for l in AGY_LABELS if l in cfg.get("agy_items", AGY_LABELS)] or list(AGY_LABELS)
    cfg["agy_items"] = agy_items
    return cfg


def save_cfg(cfg: dict) -> None:
    try:
        PLUGIN_CFG.parent.mkdir(parents=True, exist_ok=True)
        PLUGIN_CFG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


# ---------- 1. Antigravity (agy) 조회 ----------
def _decode_keyring_blob(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("go-keyring-base64:"):
        raw = base64.b64decode(raw.split(":", 1)[1]).decode("utf-8")
    obj = json.loads(raw)
    return obj.get("token", obj) if isinstance(obj, dict) else {}


def read_agy_token() -> dict:
    # 1순위: OS 보안 저장소의 gemini:antigravity (agy CLI 표준)
    try:
        if IS_MAC:
            raw = subprocess.run(
                ["security", "find-generic-password", "-s", "gemini", "-a", "antigravity", "-w"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            tok = _decode_keyring_blob(raw)
            if tok.get("access_token"):
                return tok
        elif IS_WIN:
            import ctypes
            from ctypes import wintypes as w

            class CRED(ctypes.Structure):
                _fields_ = [
                    ("Flags", w.DWORD),
                    ("Type", w.DWORD),
                    ("TargetName", w.LPWSTR),
                    ("Comment", w.LPWSTR),
                    ("LastWritten", w.FILETIME),
                    ("CredentialBlobSize", w.DWORD),
                    ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                    ("Persist", w.DWORD),
                    ("AttributeCount", w.DWORD),
                    ("Attributes", ctypes.c_void_p),
                    ("TargetAlias", w.LPWSTR),
                    ("UserName", w.LPWSTR),
                ]

            p = ctypes.POINTER(CRED)()
            if ctypes.windll.advapi32.CredReadW("gemini:antigravity", 1, 0, ctypes.byref(p)):
                try:
                    c = p.contents
                    raw = bytes(c.CredentialBlob[: c.CredentialBlobSize]).decode("utf-8")
                finally:
                    ctypes.windll.advapi32.CredFree(p)
                tok = _decode_keyring_blob(raw)
                if tok.get("access_token"):
                    return tok
    except Exception:  # noqa: BLE001
        pass

    # 2순위: ~/.gemini/oauth_creds.json 폴백
    oauth_file = HOME / ".gemini" / "oauth_creds.json"
    if oauth_file.exists():
        raw_obj = json.loads(oauth_file.read_text(encoding="utf-8"))
        tok = raw_obj.get("token", raw_obj) if isinstance(raw_obj, dict) else {}
        if tok.get("access_token"):
            return tok

    raise FileNotFoundError("Antigravity 로그인 필요")


def _is_agy_token_expired(tok: dict) -> bool:
    exp = tok.get("expiry")
    if isinstance(exp, str) and exp:
        exp_clean = re.sub(r"(\.\d{6})\d+", r"\1", exp.replace("Z", "+00:00"))
        try:
            return datetime.fromisoformat(exp_clean).timestamp() < time.time()
        except ValueError:
            pass
    exp_date = tok.get("expiry_date")
    if isinstance(exp_date, (int, float)) and exp_date > 0:
        # expiry_date in ms or s
        ts = exp_date / 1000.0 if exp_date > 1e11 else float(exp_date)
        return ts < time.time()
    return False


def fetch_antigravity() -> dict:
    try:
        try:
            tok = read_agy_token()
        except (FileNotFoundError, subprocess.CalledProcessError, PermissionError):
            return {"error": "Antigravity 로그인 필요 (agy 실행 후 Google 로그인)", "short": "로그인"}
        if _is_agy_token_expired(tok):
            return {"error": "토큰 만료 - agy 를 한 번 실행하세요", "short": "만료", "retry": 120_000}

        t = tok["access_token"]
        err: Exception | None = None
        q: dict = {}
        for host in ("daily-cloudcode-pa.googleapis.com", "cloudcode-pa.googleapis.com"):
            base = f"https://{host}/v1internal"
            try:
                load = http_json(
                    f"{base}:loadCodeAssist",
                    t,
                    {"metadata": {"ideType": "ANTIGRAVITY"}},
                    headers=AGY_HEADERS,
                )
                project = load.get("cloudaicompanionProject")
                if isinstance(project, dict):
                    project = project.get("id")
                q = http_json(
                    f"{base}:fetchAvailableModels",
                    t,
                    {"project": project} if project else {},
                    headers=AGY_HEADERS,
                )
                break
            except urllib.error.HTTPError as e:
                err = e
                if e.code in (401, 403, 429):
                    raise
        else:
            if err:
                raise err

        groups: dict[str, tuple[float, int]] = {}
        for mid, m in (q.get("models") or {}).items():
            qi = m.get("quotaInfo") or {}
            if qi.get("remainingFraction") is None or not qi.get("resetTime"):
                continue
            g = (
                "Gemini"
                if mid.startswith("gemini")
                else "Claude·GPT"
                if mid.startswith(("claude", "gpt"))
                else None
            )
            if not g:
                continue
            frac = float(qi["remainingFraction"])
            reset_ms = int(datetime.fromisoformat(qi["resetTime"].replace("Z", "+00:00")).timestamp() * 1000)
            if g not in groups or frac < groups[g][0]:
                groups[g] = (frac, reset_ms)

        rows = []
        for g in ("Gemini", "Claude·GPT"):
            if g in groups:
                frac, reset_ms = groups[g]
                rows.append({"label": f"{g} 5시간", "remain": max(0.0, frac * 100.0), "resetMs": reset_ms})
        return {"rows": rows} if rows else {"error": "쿼터 정보 없음", "short": "없음"}
    except Exception as e:  # noqa: BLE001
        return err_dict(e, "agy")


# ---------- 2. Claude 조회 ----------
def read_claude_oauth() -> dict:
    f = HOME / ".claude" / ".credentials.json"
    if f.exists():
        raw = f.read_text(encoding="utf-8")
    elif IS_MAC:
        raw = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    else:
        raise FileNotFoundError("Claude Code 로그인 정보 없음")
    return json.loads(raw)["claudeAiOauth"]


def fetch_claude() -> dict:
    try:
        try:
            oauth = read_claude_oauth()
        except (FileNotFoundError, subprocess.CalledProcessError, KeyError, PermissionError):
            return {"error": "Claude Code 로그인 정보 없음", "short": "로그인"}
        exp = oauth.get("expiresAt")
        if exp and exp < time.time() * 1000:
            return {"error": "토큰 만료 - Claude Code 실행 시 자동 갱신", "short": "만료", "retry": 60_000}
        d = http_json(
            "https://api.anthropic.com/api/oauth/usage",
            oauth["accessToken"],
            headers={"anthropic-beta": "oauth-2025-04-20"},
        )
        rows = []
        for label, key in (("5시간", "five_hour"), ("주간", "seven_day")):
            v = d.get(key)
            if v:
                reset_ms = int(datetime.fromisoformat(v["resets_at"]).timestamp() * 1000)
                rows.append({"label": label, "remain": max(0.0, 100.0 - float(v["utilization"])), "resetMs": reset_ms})
        return {"rows": rows} if rows else {"error": "사용량 응답 없음", "short": "오류"}
    except Exception as e:  # noqa: BLE001
        return err_dict(e, "Claude Code")


def fetch_claude_shared(force: bool = False) -> dict:
    """Claude Code 플러그인(ai-usage) 및 데스크톱 위젯과 ~/.claude/ai-usage-cache.json 공유"""
    now = int(time.time() * 1000)
    sh: dict = {}
    try:
        if SHARED_CLAUDE.exists():
            sh = json.loads(SHARED_CLAUDE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass

    view = sh.get("view")
    until = int(sh.get("until") or 0)
    last_t = int(sh.get("t") or 0)
    if view and (now < until or (not force and now - last_t < MIN_INTERVAL_CLAUDE_MS)):
        return view

    d = fetch_claude()
    good = sh.get("good")
    if "rows" in d:
        view = good = {"rows": d["rows"]}
        until = 0
    else:
        until = now + int(d.get("retry") or 0)
        if good and good.get("rows"):
            view = {"rows": good["rows"], "stale": d["error"], "short": d.get("short", "")}
        else:
            view = {"error": d["error"], "short": d.get("short", "")}
    try:
        SHARED_CLAUDE.parent.mkdir(parents=True, exist_ok=True)
        SHARED_CLAUDE.write_text(
            json.dumps({"t": now, "until": until, "view": view, "good": good}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001
        pass
    return view


# ---------- 3. Codex 조회 ----------
def fetch_codex_local() -> dict:
    try:
        sessions_dir = HOME / ".codex" / "sessions"
        if not sessions_dir.exists():
            return {"error": "Codex 사용 기록 없음", "short": "기록없음"}
        files = sorted(sessions_dir.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:6]
        best_ts, best = "", None
        for f in files:
            with open(f, "rb") as fh:
                fh.seek(0, os.SEEK_END)
                size = fh.tell()
                fh.seek(max(0, size - 400_000))
                lines = fh.read().decode("utf-8", "ignore").splitlines()
            for line in reversed(lines):
                if '"rate_limits"' not in line:
                    continue
                try:
                    o = json.loads(line)
                    rl = o["payload"]["rate_limits"]
                    if not rl or not rl.get("primary"):
                        continue
                except Exception:  # noqa: BLE001
                    continue
                if o["timestamp"] > best_ts:
                    best_ts, best = o["timestamp"], rl
                break
        if not best:
            return {"error": "Codex 사용 기록 없음", "short": "기록없음"}
        now_s = time.time()
        rows = []
        for label, w in (("5시간", best["primary"]), ("주간", best.get("secondary"))):
            if not w:
                continue
            used = 0.0 if w["resets_at"] < now_s else float(w["used_percent"])
            rows.append(
                {
                    "label": label,
                    "remain": max(0.0, 100.0 - used),
                    "resetMs": int(float(w["resets_at"]) * 1000),
                }
            )
        return {"rows": rows}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:50], "short": "오류"}


def fetch_codex_live() -> dict:
    auth_file = HOME / ".codex" / "auth.json"
    if not auth_file.exists():
        raise FileNotFoundError("Codex 로그인 정보 없음")
    a = json.loads(auth_file.read_text(encoding="utf-8"))
    t = a["tokens"]
    h = {"chatgpt-account-id": t["account_id"]} if t.get("account_id") else {}
    d = http_json("https://chatgpt.com/backend-api/wham/usage", t["access_token"], headers=h)
    rl = d["rate_limit"]
    rows = []
    for label, key in (("5시간", "primary_window"), ("주간", "secondary_window")):
        w = rl.get(key)
        if w:
            rows.append(
                {
                    "label": label,
                    "remain": max(0.0, 100.0 - float(w["used_percent"])),
                    "resetMs": int(float(w["reset_at"]) * 1000),
                }
            )
    if not rows:
        raise ValueError("Codex 사용량 응답 없음")
    return {"rows": rows}


def fetch_codex() -> dict:
    try:
        return fetch_codex_live()
    except Exception as e:  # noqa: BLE001
        local = fetch_codex_local()
        if "rows" in local:
            reason = err_dict(e, "Codex")["error"]
            return {"rows": local["rows"], "stale": f"실시간 조회 실패, 로컬 기록 기준 ({reason})"}
        if isinstance(e, FileNotFoundError):
            return {"error": "Codex 로그인 정보 없음", "short": "로그인"}
        return err_dict(e, "Codex")


# ---------- 통합 캐시 (~/.gemini/agy-usage-cache.json) ----------
def read_shared_cache() -> dict:
    try:
        if SHARED_AGY.exists():
            return json.loads(SHARED_AGY.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    return {}


def write_shared_cache(cache: dict) -> None:
    try:
        SHARED_AGY.parent.mkdir(parents=True, exist_ok=True)
        SHARED_AGY.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def get_cached_provider(cache: dict, name: str, fn, min_interval_ms: int, force: bool = False) -> dict:
    now = int(time.time() * 1000)
    providers = cache.setdefault("providers", {})
    st = providers.setdefault(name, {"t": 0, "until": 0, "view": None, "good": None})
    if st.get("view") and (now < st.get("until", 0) or (not force and now - st.get("t", 0) < min_interval_ms)):
        return st["view"]

    st["t"] = now
    d = fn()
    if "rows" in d:
        st["good"] = {"rows": d["rows"]}
        st["until"] = 0
        st["view"] = d
    else:
        st["until"] = now + int(d.get("retry") or 0)
        if st.get("good") and st["good"].get("rows"):
            st["view"] = {"rows": st["good"]["rows"], "stale": d["error"], "short": d.get("short", "")}
        else:
            st["view"] = {"error": d["error"], "short": d.get("short", "")}
    return st["view"]


def fetch_all(cfg: dict, force: bool = False) -> dict[str, dict]:
    cache = read_shared_cache()
    enabled = cfg.get("enabled", ["Antigravity", "Claude", "Codex"])
    agy_items = cfg.get("agy_items", list(AGY_LABELS))
    results: dict[str, dict] = {}

    for name in enabled:
        if name == "Antigravity":
            d = get_cached_provider(cache, "Antigravity", fetch_antigravity, MIN_INTERVAL_AGY_MS, force=force)
            if "rows" in d:
                filtered = [r for r in d["rows"] if r["label"] in agy_items] or d["rows"]
                d = {**d, "rows": filtered}
            results[name] = d
        elif name == "Claude":
            results[name] = fetch_claude_shared(force=force)
        elif name == "Codex":
            results[name] = get_cached_provider(cache, "Codex", fetch_codex, MIN_INTERVAL_CODEX_MS, force=force)

    write_shared_cache(cache)
    return results


# ---------- 포맷팅 ----------
def dot(remain: float) -> str:
    return "🟢" if remain >= 40 else "🟡" if remain >= 15 else "🔴"


def progress_bar(remain: float, width: int = 10) -> str:
    filled = max(0, min(width, round((remain / 100.0) * width)))
    return "█" * filled + "░" * (width - filled)


def short_reset(ms: int | None, tilde: bool = False) -> str:
    if not ms:
        return ""
    dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).astimezone()
    near = (ms / 1000.0 - time.time()) < 86_400
    s = f"{dt:%H:%M}" if near else f"{dt.month}/{dt.day} {dt:%H:%M}"
    return ("~" if tilde else "") + s


def format_status_line(results: dict[str, dict], include_unconfigured: bool = False) -> str:
    parts = []
    for name, d in results.items():
        rows = d.get("rows") or []
        if not rows:
            # Antigravity는 항상 표시하고, 다른 AI는 로그인 정보가 없을 때 상태줄에서 생략 가능
            if name != "Antigravity" and d.get("short") in ("로그인", "기록없음") and not include_unconfigured:
                continue
            parts.append(f"`{name}` ⚠{d.get('short') or '확인'}")
            continue
        cells = []
        for r in rows:
            lbl = SHORT.get(r["label"], r["label"])
            rem = round(float(r["remain"]))
            rst = short_reset(r.get("resetMs"), tilde=True)
            rst_str = f" ({rst})" if rst else ""
            cells.append(f"{dot(rem)}{lbl} **{rem}%**{rst_str}")
        stale_mark = " ~" if d.get("stale") else ""
        parts.append(f"`{name}` " + " ".join(cells) + stale_mark)
    return "  ｜  ".join(parts) if parts else "`AI Usage` ⚠ 조회 가능한 AI 로그인 정보가 없습니다"


def format_detail_markdown(results: dict[str, dict], cfg: dict) -> str:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"### 📊 AI 남은 사용량 (`{now_str}` 기준)",
        "",
        "| AI | 구간 | 남은 사용량 | 상태 | 갱신 시각 | 비고 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for name, d in results.items():
        rows = d.get("rows") or []
        if not rows:
            err = d.get("error", "조회 실패")
            lines.append(f"| **{name}** | - | - | ⚠ `{d.get('short', '오류')}` | - | {err} |")
            continue
        note = f"⚠ 이전 값 ({d['stale']})" if d.get("stale") else "정상"
        for i, r in enumerate(rows):
            ai_col = f"**{name}**" if i == 0 else ""
            rem = float(r["remain"])
            bar = progress_bar(rem, 10)
            rst = short_reset(r.get("resetMs"))
            lines.append(
                f"| {ai_col} | {r['label']} | `{bar}` **{rem:.0f}%** | {dot(rem)} | `{rst}` | {note if i == 0 else ''} |"
            )

    en_str = ", ".join(cfg.get("enabled", []))
    agy_str = ", ".join(cfg.get("agy_items", []))
    lines.extend(
        [
            "",
            f"- **표시 중인 AI**: `{en_str}` (Antigravity 세부 항목: `{agy_str}`)",
            "- **캐시 정책**: 429 요청 제한 방지를 위해 최대 2~3분 간격으로 서버를 조회하며, 오류 시 마지막 정상값을 유지합니다.",
        ]
    )
    return "\n".join(lines)


# ---------- Antigravity Hook 핸들러 ----------
def handle_hook(event: str) -> None:
    try:
        raw_in = sys.stdin.read()
        payload = json.loads(raw_in) if raw_in.strip() else {}
    except Exception:  # noqa: BLE001
        payload = {}

    conv_id = payload.get("conversationId") or "default"
    last_input = payload.get("lastUserInput") or ""

    cache = read_shared_cache()
    turns = cache.setdefault("turns", {})

    # PreInvocation 은 한 프롬프트 내 여러 툴 호출마다 반복 실행되므로,
    # 동일한 사용자 입력(턴)에서는 첫 번째 호출에만 상태줄을 표시한다.
    if event == "pre_invocation":
        prev_input = turns.get(conv_id)
        if not last_input or prev_input == last_input:
            print("{}")
            return
        turns[conv_id] = last_input
        # 오래된 세션 키 정리 (최대 50개 유지)
        if len(turns) > 50:
            for k in list(turns.keys())[:-50]:
                turns.pop(k, None)
        write_shared_cache(cache)

    cfg = load_cfg()
    results = fetch_all(cfg, force=False)
    line = format_status_line(results, include_unconfigured=False)

    out = {
        "injectSteps": [
            {
                "systemMessage": {
                    "systemMessage": "",
                    "metadata": {
                        "user_markdown": line,
                    },
                }
            }
        ]
    }
    print(json.dumps(out, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Antigravity (agy) · Claude · Codex 남은 사용량 조회 도구")
    parser.add_argument("--hook", choices=["session_start", "pre_invocation"], help="Antigravity 훅 모드로 실행")
    parser.add_argument("--detail", action="store_true", help="상세 마크다운 표 출력")
    parser.add_argument("--compact", action="store_true", help="한 줄 상태줄 출력")
    parser.add_argument("--json", action="store_true", help="원시 JSON 출력")
    parser.add_argument("--refresh", action="store_true", help="캐시 주기를 무시하고 즉시 재조회 (429 백오프는 유지)")
    parser.add_argument(
        "--enable",
        nargs="+",
        choices=ALL_PROVIDERS,
        help="표시할 AI 목록 설정 (예: --enable Antigravity Claude)",
    )
    parser.add_argument(
        "--agy-items",
        nargs="+",
        choices=AGY_LABELS,
        help="Antigravity 표시 항목 설정 (예: --agy-items 'Gemini 5시간' 'Claude·GPT 5시간')",
    )
    args = parser.parse_args()

    if args.hook:
        try:
            handle_hook(args.hook)
        except Exception:  # noqa: BLE001
            print("{}")
        return

    cfg = load_cfg()
    cfg_changed = False
    if args.enable:
        cfg["enabled"] = [p for p in ALL_PROVIDERS if p in args.enable]
        cfg_changed = True
    if args.agy_items:
        cfg["agy_items"] = [i for i in AGY_LABELS if i in args.agy_items]
        cfg_changed = True
    if cfg_changed:
        save_cfg(cfg)

    results = fetch_all(cfg, force=args.refresh)
    if args.json:
        print(json.dumps({"config": cfg, "results": results}, ensure_ascii=False, indent=2))
    elif args.detail:
        print(format_detail_markdown(results, cfg))
    else:
        print(format_status_line(results, include_unconfigured=True))


if __name__ == "__main__":
    main()
