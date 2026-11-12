---
name: agy-usage
description: >-
  Check remaining AI usage limits (5-hour and weekly quotas) and reset times for
  Antigravity (Gemini / Claude·GPT 5-hour), Claude Code, and OpenAI Codex. Use
  this skill when the user runs /agy-usage or asks to check remaining quota,
  usage percentage, rate limits, reset times, or configure which AI providers
  appear in the usage status line.
---

# AI Usage (`agy-usage`)

Use this skill to display or configure remaining usage quotas (5-hour and weekly) and reset times for **Antigravity (`agy`)**, **Claude**, and **Codex**.

## Commands

Run the bundled `usage.py` script located at `../../scripts/usage.py` relative to this `SKILL.md` file (or `~/.gemini/config/plugins/agy-usage/scripts/usage.py`):

1. **Detailed Usage Report (Default for `/agy-usage`)**:
   ```bash
   python ~/.gemini/config/plugins/agy-usage/scripts/usage.py --detail
   ```
   *(On macOS/Linux where `python` is `python3`, use `python3`.)*

2. **Force Refresh**:
   When the user asks to refresh usage right now:
   ```bash
   python ~/.gemini/config/plugins/agy-usage/scripts/usage.py --detail --refresh
   ```

3. **Change Displayed AI Providers or Antigravity Groups**:
   - Choose which AIs to show (`Antigravity`, `Claude`, `Codex`):
     ```bash
     python ~/.gemini/config/plugins/agy-usage/scripts/usage.py --enable Antigravity Claude --detail
     ```
   - Choose which Antigravity model groups to show (`"Gemini 5시간"`, `"Claude·GPT 5시간"`):
     ```bash
     python ~/.gemini/config/plugins/agy-usage/scripts/usage.py --agy-items "Gemini 5시간" "Claude·GPT 5시간" --detail
     ```

## Output Guidelines

- Note that the terminal sandbox blocks external network access and OS credential manager reads by default. If running `usage.py` inside the sandbox returns a network or login error (`네트워크 연결 확인` or `로그인 필요`), re-run the command with `BypassSandbox: true` so it can read the OS credential store (`gemini:antigravity` / `~/.claude/.credentials.json` / `~/.codex/auth.json`) and query the official usage endpoints.
- Present the markdown table produced by `--detail` directly to the user.
