---
name: agy-usage
description: >-
  Check remaining Antigravity AI usage limits and reset times, especially
  Gemini 4 Argon weekly quota, Gemini Flash (5-hour), and Claude/GPT (5-hour).
  Use this skill when the user runs /usage, /agy-usage, or asks to check
  Argon weekly quota, remaining percentages, rate limits, or reset times.
---

# Antigravity Usage (`agy-usage`)

Antigravity의 실시간 AI 남은 사용량과 리셋 시각을 확인합니다.

- **Gemini 4 Argon**: 7일 단위 **주간 한도 (Weekly)**
- **Gemini Flash (Gemini 3.8 Flash 등)**: **5시간 한도 (5-hour rolling)**
- **Claude · GPT**: **5시간 한도 (5-hour rolling)**

## 실행 명령

```bash
# 한 줄 요약 상태
python ~/.gemini/config/plugins/agy-usage/scripts/usage.py

# 상세 진행률 막대 및 리셋 시각 표 출력 (/usage 기본 동작)
python ~/.gemini/config/plugins/agy-usage/scripts/usage.py --detail

# 캐시 무시하고 즉시 재조회
python ~/.gemini/config/plugins/agy-usage/scripts/usage.py --detail --refresh
```
