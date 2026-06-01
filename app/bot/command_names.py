"""Имена команд Telegram — участник vs ведущий группы.

Паттерн: my_goals_* / view_my_goals; group_* для ведущего.
"""

# --- Участник: goals ---
CMD_MY_GOALS_SET = "my_goals_set"
CMD_VIEW_MY_GOALS = "view_my_goals"
CMD_MY_GOALS_SUBMIT = "my_goals_submit"
CMD_MY_GOALS_UPDATE = "my_goals_update"

# --- Ведущий: goals из транскрипта (Plaud) ---
CMD_GROUP_PASTE_TRANSCRIPT = "group_paste_transcript"
CMD_GROUP_PASTE_DONE = "group_paste_done"
CMD_GROUP_SET_PLAUD = "group_set_plaud"

# --- Ведущий: goals (все участники) ---
CMD_GROUP_VIEW_GOALS = "group_view_goals"
CMD_GROUP_SYNC_GOALS = "group_sync_goals"

# --- Ведущий: участники и заявки ---
CMD_GROUP_INVITE = "group_invite"
CMD_GROUP_MEMBERS = "group_members"
CMD_GROUP_REQUESTS = "group_requests"
