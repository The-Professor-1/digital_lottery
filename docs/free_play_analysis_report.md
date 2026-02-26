# Free Play / Allow System Account — Analysis Report

**Purpose:** When "Free play" is **unticked** (and system accounts are allowed), the expectation is that only fake users win. This report analyzes the code flow and identifies **critical** or **likely** issues that can explain why real users still win sometimes. **No code changes were made** for this report.

---

## 1. Game-level settings cache (critical)

**Where:** `backend/api/game_logic.py` — `start_game()`  
**What happens:** When a game starts, global `GameSettings` (including `free_play`) are read once and stored in Redis under `game:{game.id}:settings` for **1 hour** (3600 seconds).

**Impact:**  
- If you **untick Free play** after a game has **already started**, that game keeps using the **old** cached value (e.g. `free_play = True`).  
- So for the whole duration of that game, number calling and claim logic still behave as "free play": numbers can be random and real users can win.  
- Only **newly started** games (started after you unticked) use `free_play = False`.

**Conclusion:** This is a **critical** reason you still see real winners after unticking: any game that was already running continues in “free play” mode until it ends or the cache expires.

---

## 2. Auto number calling and the cache

**Where:** `backend/api/tasks.py` — `task_auto_call_numbers`  
**Behavior:** The task calls `GameSettings.get_settings(game_id=game_id)`. In `models.py`, when `game_id` is provided, `get_settings()` returns the **cached** game-level settings if present (see §1). So for an active game, `free_play` used here is the one cached at **game start**, not the current checkbox in the UI.

When `allow_system_account` is True and `free_play` is False (from cache), the task uses `get_safe_number_to_call(game, called_numbers_set, free_play=False)` to pick a number. So **for that game**, the *intended* behavior (only safe numbers) is used only if the cache already has `free_play=False` (i.e. game was started after you unticked).

---

## 3. Safe-number fallback when no “safe” number exists (critical)

**Where:** `backend/api/fake_user_manager.py` — `get_safe_number_to_call()`  
**Logic when `free_play` is False:**  
- It computes numbers that would make **real** users win (`blocking_numbers`).  
- `safe_numbers = available - blocking_numbers`.  
- If `safe_numbers` is **not** empty, it returns one of those (preferring numbers that help fake users).  
- If `safe_numbers` **is** empty (every remaining number would give a real user bingo), the code does:

```python
else:
    # All numbers would let real users win - call a random one anyway
    # (This shouldn't happen in normal gameplay)
    return random.choice(list(available))
```

So in that edge case, it **still calls a number** and that number can make a **real** user win.

**Conclusion:** This is a **critical** bug when free_play is off: in late game, when every remaining number completes at least one real user’s card, the system falls back to a random number and can crown a real winner.

---

## 4. Manual number calling (likely)

**Where:**  
- `backend/api/admin_views.py` — `call_number_api`  
- `backend/api/views.py` — `call_number_admin`  

**Behavior:** The admin (or second admin) sends a **specific** number to call. The backend runs `task_call_number.delay(game_id, number)` and does **not** use `get_safe_number_to_call` or check `free_play`. So the chosen number is whatever the admin picked.

**Conclusion:** If any numbers are called **manually** while free_play is off, the backend does **not** enforce “only safe numbers.” Real users can win from manually called numbers. This is a **likely** cause if you use manual calling.

---

## 5. Claim logic (priority when free_play is off)

**Where:** `backend/api/game_logic.py` — `process_bingo_claim()`  
**Behavior:** It uses `GameSettings.get_settings(game_id=game.id)`, so again it uses **cached** game-level settings. If the cache has `free_play=False`, then when a **fake** user claims, the code checks whether any **real** user has bingo and, if so, rejects the fake claim with “Real user has priority (free_play is OFF).” So claim priority is correct **for that game** when the cache already has `free_play=False`. The issue is not here but in (1) which games get that cached value and (2) which numbers get called (§2 and §3).

---

## Summary

| Issue | Severity | Effect |
|-------|----------|--------|
| Game-level cache of `free_play` at start; unticking mid-game doesn’t affect already-started games | **Critical** | Already-running games keep “free play” behavior; real users can win until the game ends or cache expires. |
| `get_safe_number_to_call` fallback when no safe number exists | **Critical** | In late game, a random number can be called and a real user can win even when free_play is off. |
| Manual number calling ignores `free_play` and safe-number logic | **Likely** | Any manually called number can let a real user win. |

**Recommendation (for when you implement fixes):**  
1. Consider invalidating or not using the game-level settings cache when the admin changes `free_play` (or accept that only **new** games respect the change).  
2. When `free_play` is off and there is no safe number, avoid calling a number that gives a real user bingo (e.g. skip calling, or end game / declare fake winner per your product rules).  
3. For manual number calling, when `free_play` is off, either restrict to “safe” numbers only or clearly document that manual calls can let real users win.
