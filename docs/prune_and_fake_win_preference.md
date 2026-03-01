# Prune data & Fake win preference

## Cached games played (prune-safe)

- **User fields** (survive prune): `total_games_played`, `total_wins`, `total_deposits_amount`, `total_withdrawals_amount`.
- **Updated when**: A game completes (`record_game_completed` in `stats_utils`), deposits/withdrawals are recorded.
- **Used everywhere**: Admin dashboard (registered users table, user detail, search user) and API user list now use these cached values so after you prune old games, **games played and wins counts do not drop** for users.
- **Prune command**: `python manage.py prune_old_data --keep 50` (or `--keep 20`). Keeps last N games; never deletes users or transactions. See `backend/api/management/commands/prune_old_data.py`.

---

## Fake win preference (admin dashboard)

**Location**: Admin Dashboard → Game Settings → **Fake win preference** (shown only when “Allow system account” is on and “Free play” is off).

| Level | Behavior |
|-------|----------|
| **0 (Default)** | Current behavior. No extra work: when a safe number exists, prefer one that helps a fake win; otherwise any safe number. If no safe number, call at random (real user may win). |
| **1** | Prefer fake wins when safe: among numbers that don’t let real users win, pick the number that helps **the most** system (fake) cards get bingo. Game flow looks normal. |
| **2** | Same as 1, plus **when there is no safe number** (every remaining number would let some real user win), pick the number that **maximizes system wins** (and minimizes real wins). Still looks like normal draw; backend biases toward system. |

- **Free play**: When “Free play” is on, number calling is always random (no preference logic).
- **Game start**: The level is cached at game start, so changing it in settings does not affect already-started games.
