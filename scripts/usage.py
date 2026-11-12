#!/usr/bin/env python3
"""Antigravity (agy) 전용 AI 남은 사용량 플러그인 스크립트

- Gemini 4 Argon (주간 쿼터)
- Gemini Flash (5시간 쿼터)
- Claude · GPT (5시간 쿼터)

Antigravity 내부 Language Server RPC(GetUserStatus) 및 보안 저장소(gemini:antigravity)를 통해
현재 세션의 실시간 쿼터 및 갱신 시각을 조회합니다.
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

CACHE_FILE = HOME / ".gemini" / "agy-usage-cache.json"
CACHE_TTL_MS = 60_000  # 1분 로컬 캐시
AGY_HEADERS = {"User-Agent": "antigravity"}


# ---------- 1. Language Server RPC (GetUserStatus) ----------
def fetch_from_language_server() -> list[dict] | None:
    addr = os.environ.get("ANTIGRAVITY_LS_ADDRESS")
    csrf = os.environ.get("ANTIGRAVITY_CSRF_TOKEN")
    if not addr or not csrf:
        return None
    url = f"http://{addr}/exa.language_server_pb.LanguageServerService/GetUserStatus"
    req = urllib.request.Request(
        url,
        data=b"{}",
        headers={"Content-Type": "application/json", "x-codeium-csrf-token": csrf},
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.load(r)
        configs = (
            data.get("userStatus", {})
            .get("cascadeModelConfigData", {})
            .get("clientModelConfigs", [])
        )
        return parse_client_configs(configs)
    except Exception:  # noqa: BLE001
        return None


def parse_client_configs(configs: list[dict]) -> list[dict]:
    """clientModelConfigs 에서 Argon(주간), Flash(5h), Claude/GPT(5h) 추출"""
    groups: dict[str, dict] = {}
    for c in configs:
        label = c.get("label") or ""
        q = c.get("quotaInfo") or {}
        frac = q.get("remainingFraction")
        reset_str = q.get("resetTime")
        if frac is None or not reset_str:
            continue
        try:
            reset_ms = int(
                datetime.fromisoformat(reset_str.replace("Z", "+00:00")).timestamp() * 1000
            )
        except Exception:
            continue

        remain = max(0.0, min(100.0, float(frac) * 100.0))

        # 1) Argon (주간 한도)
        if "Argon" in label:
            g_key = "Argon"
            g_name = "Gemini 4 Argon"
            window = "주간"
        # 2) Flash (5시간 한도)
        elif "Flash" in label:
            g_key = "Flash"
            g_name = "Gemini Flash"
            window = "5시간"
        # 3) Claude / GPT (5시간 한도)
        elif any(k in label for k in ("Claude", "GPT", "Opus", "Sonnet")):
            g_key = "ClaudeGPT"
            g_name = "Claude · GPT"
            window = "5시간"
        else:
            continue

        # 같은 그룹 중 최소 잔여량(또는 가장 이른 리셋) 유지
        if g_key not in groups or remain < groups[g_key]["remain"]:
            groups[g_key] = {
                "key": g_key,
                "name": g_name,
                "window": window,
                "label": f"{g_name} ({window})",
                "remain": remain,
                "resetMs": reset_ms,
            }

    # 정렬: Argon(주간) 우선, 그 다음 Flash(5시간), Claude·GPT(5시간)
    order = ["Argon", "Flash", "ClaudeGPT"]
    return [groups[k] for k in order if k in groups]


# ---------- 2. Fallback: OS 보안 저장소 토큰 + cloudcode API ----------
def _decode_keyring_blob(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("go-keyring-base64:"):
        raw = base64.b64decode(raw.split(":", 1)[1]).decode("utf-8")
    obj = json.loads(raw)
    return obj.get("token", obj) if isinstance(obj, dict) else {}


def read_agy_token() -> dict:
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

    oauth_file = HOME / ".gemini" / "oauth_creds.json"
    if oauth_file.exists():
        try:
            raw_obj = json.loads(oauth_file.read_text(encoding="utf-8"))
            tok = raw_obj.get("token", raw_obj) if isinstance(raw_obj, dict) else {}
            if tok.get("access_token"):
                return tok
        except Exception:  # noqa: BLE001
            pass

    raise FileNotFoundError("Antigravity 로그인 필요")


def fetch_from_cloudcode_api() -> list[dict]:
    tok = read_agy_token()
    t = tok["access_token"]
    for host in ("cloudcode-pa.googleapis.com", "daily-cloudcode-pa.googleapis.com"):
        base = f"https://{host}/v1internal"
        req = urllib.request.Request(
            f"{base}:fetchAvailableModels",
            data=b"{}",
            headers={"Authorization": f"Bearer {t}", "Content-Type": "application/json", **AGY_HEADERS},
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                q = json.load(r)
            configs = []
            for mid, m in (q.get("models") or {}).items():
                configs.append({"label": m.get("displayName") or mid, "quotaInfo": m.get("quotaInfo")})
            rows = parse_client_configs(configs)
            if rows:
                return rows
        except Exception:  # noqa: BLE001
            continue
    raise ValueError("Antigravity 쿼터 정보를 조회할 수 없습니다.")


# ---------- 캐시 관리 ----------
def read_cache() -> dict:
    try:
        if CACHE_FILE.exists():
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    return {}


def write_cache(data: dict) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def get_usage(force: bool = False) -> dict:
    now = int(time.time() * 1000)
    cache = read_cache()
    cached_rows = cache.get("rows")
    last_t = int(cache.get("t") or 0)

    if not force and cached_rows and (now - last_t < CACHE_TTL_MS):
        return {"rows": cached_rows, "cached": True}

    # 1순위: Language Server RPC (가장 정확한 Argon 주간 쿼터 포함)
    rows = fetch_from_language_server()

    # 2순위: cloudcode API
    if not rows:
        try:
            rows = fetch_from_cloudcode_api()
        except Exception as e:  # noqa: BLE001
            if cached_rows:
                return {"rows": cached_rows, "stale": str(e), "cached": True}
            return {"error": str(e), "rows": []}

    if rows:
        cache["rows"] = rows
        cache["t"] = now
        write_cache(cache)
        return {"rows": rows, "cached": False}

    return {"error": "쿼터 정보를 찾을 수 없습니다.", "rows": []}


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


def format_status_line(res: dict) -> str:
    rows = res.get("rows") or []
    if not rows:
        err = res.get("error", "로그인 확인 필요")
        return f"`Antigravity` ⚠{err}"

    parts = []
    for r in rows:
        key = r["key"]
        tag = "Argon(주)" if key == "Argon" else "Flash(5h)" if key == "Flash" else "Cl·GPT(5h)"
        rem = round(float(r["remain"]))
        rst = short_reset(r.get("resetMs"), tilde=True)
        rst_str = f" ({rst})" if rst else ""
        parts.append(f"{dot(rem)}{tag} **{rem}%**{rst_str}")

    stale = " ~" if res.get("stale") else ""
    return "`Antigravity` " + "  ".join(parts) + stale


def format_detail_markdown(res: dict) -> str:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = res.get("rows") or []
    lines = [
        f"### 📊 Antigravity AI 남은 사용량 (`{now_str}` 기준)",
        "",
        "| 모델 그룹 | 주기 | 남은 사용량 | 상태 | 갱신 시각 (리셋) | 비고 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    if not rows:
        lines.append(f"| Antigravity | - | - | ⚠ 오류 | - | {res.get('error', '조회 실패')} |")
    else:
        for r in rows:
            rem = float(r["remain"])
            bar = progress_bar(rem, 10)
            rst = short_reset(r.get("resetMs"))
            note = "주간 한도" if r["window"] == "주간" else "5시간 한도"
            lines.append(
                f"| **{r['name']}** | `{r['window']}` | `{bar}` **{rem:.1f}%** | {dot(rem)} | `{rst}` | {note} |"
            )

    if res.get("stale"):
        lines.extend(["", f"> ⚠ 최근 갱신 실패로 이전 캐시 값을 표시 중입니다: {res['stale']}"])
    lines.extend(
        [
            "",
            "- **Argon (Gemini 4 Argon)**: 7일 단위 **주간 한도**로 관리됩니다.",
            "- **Flash (Gemini 3.8 Flash 등)** 및 **Claude · GPT**: **5시간 롤링 한도**로 관리됩니다.",
        ]
    )
    return "\n".join(lines)


# ---------- Hook 핸들러 (PreInvocation / SessionStart) ----------
def handle_hook(event: str) -> None:
    try:
        raw_in = sys.stdin.read()
        payload = json.loads(raw_in) if raw_in.strip() else {}
    except Exception:  # noqa: BLE001
        payload = {}

    conv_id = payload.get("conversationId") or "default"
    last_input = payload.get("lastUserInput") or ""

    cache = read_cache()
    turns = cache.setdefault("turns", {})

    if event == "pre_invocation":
        prev_input = turns.get(conv_id)
        if not last_input or prev_input == last_input:
            print("{}")
            return
        turns[conv_id] = last_input
        if len(turns) > 50:
            for k in list(turns.keys())[:-50]:
                turns.pop(k, None)
        write_cache(cache)

    res = get_usage(force=False)
    line = format_status_line(res)
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
    parser = argparse.ArgumentParser(description="Antigravity 남은 사용량 (Argon 주간 / Flash 5h / Claude·GPT 5h)")
    parser.add_argument("--hook", choices=["session_start", "pre_invocation"], help="Antigravity 훅 모드")
    parser.add_argument("--detail", action="store_true", help="상세 마크다운 표 출력")
    parser.add_argument("--refresh", action="store_true", help="캐시 무시하고 즉시 재조회")
    parser.add_argument("--json", action="store_true", help="JSON 출력")
    args = parser.parse_args()

    if args.hook:
        try:
            handle_hook(args.hook)
        except Exception:  # noqa: BLE001
            print("{}")
        return

    res = get_usage(force=args.refresh)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif args.detail:
        print(format_detail_markdown(res))
    else:
        print(format_status_line(res))


if __name__ == "__main__":
    main()
