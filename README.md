# agy-usage (Antigravity CLI · App 플러그인)

**Antigravity(`agy`) · Claude · Codex** 의 **남은 사용량(5시간 · 주간)과 갱신 시각**을 Antigravity CLI(`agy`) 및 Antigravity 2.0 대화창 상태줄에

```text
Antigravity 🟢Gem 85% (~18:30) 🟢Cl·GPT 92% (~18:30)  ｜  Claude 🟢5h 71% (~17:00) 🟢주 93% (~11/17 09:00)
```

처럼 자동으로 보여주고, `/agy-usage` 명령으로 진행률 막대와 갱신 시각까지 자세히 확인할 수 있는 네이티브 Antigravity 플러그인입니다.

> 데스크톱 작업표시줄(Windows) / 메뉴바(macOS)에 항상 떠 있는 위젯 앱은 [kjw0615/usage-widget](https://github.com/kjw0615/usage-widget) 저장소를 참고하세요.

---

## 주요 기능

1. **자동 상태줄 표시 (`SessionStart` / `PreInvocation` 훅)**
   - 새 세션을 시작하거나 프롬프트를 보낼 때, 모델의 컨텍스트(토큰)를 전혀 소모하지 않는 인라인 상태줄(`metadata.user_markdown`)로 남은 사용량을 표시합니다.
   - 한 프롬프트 안에서 에이전트가 여러 툴을 연속 호출하더라도 사용자 턴당 **딱 한 번만** 깔끔하게 표시됩니다.
2. **`/agy-usage` 슬래시 명령 (스킬)**
   - `/agy-usage` 입력 시 Antigravity(Gemini 5시간 · Claude·GPT 5시간), Claude(5시간 · 주간), Codex(5시간 · 주간)의 남은 비율, 진행률 막대(`████░░░░░░`), 갱신 시각을 표로 출력합니다.
   - 표시할 AI 선택(`Antigravity`, `Claude`, `Codex`) 및 Antigravity 세부 그룹(`Gemini 5시간`, `Claude·GPT 5시간`) 설정 변경을 지원합니다.
3. **요청 제한(429) 방지 및 캐시 공유**
   - 서버 조회는 2~3분 간격으로만 전송하며(`~/.gemini/agy-usage-cache.json` 및 `~/.claude/ai-usage-cache.json` 공유), 일시적인 네트워크/429 오류가 나도 마지막 정상값을 `~` 표시와 함께 유지합니다.
   - 데스크톱 위젯([usage-widget](https://github.com/kjw0615/usage-widget))의 설정 파일(`%APPDATA%\UsageWidget\config.json` 또는 `~/Library/Application Support/UsageWidget/config.json`)이 있으면 표시 항목 설정을 자동으로 연동합니다.

---

## 먼저 확인: 로그인 정보

플러그인은 **이 PC에 이미 로그인된 각 CLI/앱의 인증 토큰을 읽기만** 합니다 (별도 로그인 창 없음, 외부 전송 없음).

| AI | 읽는 위치 | 표시 항목 |
| :--- | :--- | :--- |
| **Antigravity (`agy`)** | OS 보안 저장소(`gemini:antigravity`) 또는 `~/.gemini/oauth_creds.json` | `Gemini 5시간`, `Claude·GPT 5시간` |
| **Claude** | `~/.claude/.credentials.json` (macOS는 키체인 `Claude Code-credentials`) | `5시간`, `주간` |
| **Codex** | `~/.codex/auth.json` (실패 시 `~/.codex/sessions/**/*.jsonl` 로컬 기록) | `5시간`, `주간` |

---

## 설치 방법

### 방법 1: 글로벌 플러그인 폴더에 클론 (Windows / macOS 공통)

Antigravity의 글로벌 플러그인 경로(`~/.gemini/config/plugins/agy-usage`)에 클론하면 별도 설정 없이 즉시 활성화됩니다.

```bash
git clone https://github.com/kjw0615/agy-usage.git ~/.gemini/config/plugins/agy-usage
```

PowerShell (Windows):
```powershell
git clone https://github.com/kjw0615/agy-usage.git "$HOME\.gemini\config\plugins\agy-usage"
```

### 방법 2: 터미널에서 단독 실행

플러그인에 포함된 `scripts/usage.py`는 외부 패키지 설치 없이(Python 3.10+ 표준 라이브러리만 사용) 단독 CLI 도구로도 동작합니다.

```bash
# 한 줄 요약 출력
python ~/.gemini/config/plugins/agy-usage/scripts/usage.py

# 마크다운 상세 표 출력
python ~/.gemini/config/plugins/agy-usage/scripts/usage.py --detail

# 캐시 무시하고 즉시 새로고침
python ~/.gemini/config/plugins/agy-usage/scripts/usage.py --detail --refresh

# 표시할 AI 선택 저장 (예: Antigravity와 Claude만 표시)
python ~/.gemini/config/plugins/agy-usage/scripts/usage.py --enable Antigravity Claude --detail
```

---

## 디렉터리 구조

```text
agy-usage/
├── plugin.json                 # Antigravity 플러그인 매니페스트
├── hooks.json                  # SessionStart / PreInvocation 상태줄 자동 표시 훅
├── assets/
│   └── logo.svg                # 플러그인 아이콘
├── scripts/
│   └── usage.py                # 사용량 조회·캐시·훅·CLI 통합 스크립트 (무의존성 Python 3)
└── skills/
    └── agy-usage/
        └── SKILL.md            # /agy-usage 슬래시 명령 스킬
```

## 라이선스

MIT License
