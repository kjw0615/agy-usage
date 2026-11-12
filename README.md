# agy-usage (Antigravity 전용 남은 사용량 플러그인)

**Antigravity(`agy`)** 전용으로, 특히 **Gemini 4 Argon의 주간(Weekly) 사용량**과 **Flash / Claude·GPT의 5시간 사용량**을 한눈에 확인할 수 있는 플러그인입니다.

타 AI 도구(Claude Code, Codex) 없이 **오직 Antigravity 내부 쿼터만** 깔끔하게 추적합니다.

```text
Antigravity 🟢Argon(주) 66% (~11/19 09:53)  🟢Flash(5h) 94% (~19:56)  🟢Cl·GPT(5h) 85% (~17:35)
```

---

## 주요 특징

1. **Gemini 4 Argon 주간 쿼터 완벽 지원**
   - Argon 모델에 적용되는 7일 주기 **주간 한도(Weekly Quota)** 의 잔여율(%)과 정확한 리셋 일시를 표시합니다.
2. **Flash & Claude·GPT 5시간 쿼터 분리 표시**
   - Argon(주간)과 Flash/Claude·GPT(5시간)의 리셋 주기를 구분하여 보여줍니다.
3. **자동 상태줄 표시 (`hooks.json`)**
   - 대화 시작 및 프롬프트 전송 시 토큰 소모 없이(`metadata.user_markdown`) 사용자 턴당 1회씩 인라인 상태줄을 출력합니다.
4. **`/usage` 슬래시 명령 지원**
   - 채팅창 또는 `agy` CLI에서 `/usage` 입력 시 진행률 막대와 리셋 시각이 담긴 마크다운 상세 표를 출력합니다.

---

## 설치 및 적용

```bash
git clone https://github.com/kjw0615/agy-usage.git ~/.gemini/config/plugins/agy-usage
```

PowerShell:
```powershell
git clone https://github.com/kjw0615/agy-usage.git "$HOME\.gemini\config\plugins\agy-usage"
```

---

## CLI 단독 실행

```bash
# 한 줄 상태
python ~/.gemini/config/plugins/agy-usage/scripts/usage.py

# 상세 표
python ~/.gemini/config/plugins/agy-usage/scripts/usage.py --detail

# 즉시 새로고침
python ~/.gemini/config/plugins/agy-usage/scripts/usage.py --detail --refresh
```

## 라이선스
MIT License
