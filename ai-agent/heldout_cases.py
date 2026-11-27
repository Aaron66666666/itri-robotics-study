"""24 held-out commands for the TM5S table (written 2026-11-27 night, after the
team reached 24/24 on the 12 development commands; none of them was used while
developing). Same grading as eval_team.py, and the same expectations for the
single agent and the team: what the user asked for.

  python3 eval_team.py --set heldout --backend fake --modes single team --repeat 2
"""

from robot_agent.arm_tools import AREAS

BASE = {"cup": (0.50, 0.55), "bottle": (0.33, 0.45)}
LEFT, RIGHT, CENTER = AREAS["left"][0], AREAS["right"][0], AREAS["center"][0]
NO = ["不能", "無法", "沒辦法", "只能", "不支援", "沒有", "不行"]
BLOCKED = ["占", "佔", "擋", "被", "不能", "無法", "沒辦法", "不行", "已有", "已經有"]

HELDOUT = [
    # A. the same moves, said differently
    {"id": "h_mug_left", "task": "請幫我把馬克杯移到左側", "setup": BASE,
     "expect": {"cup": "left"}, "answer_all": ["杯"]},
    {"id": "h_bottle_centre", "task": "瓶子拿去中央放", "setup": {"cup": (0.38, 0.62), "bottle": (0.55, 0.30)},
     "expect": {"bottle": "center"}, "answer_all": ["瓶"]},
    {"id": "h_english", "task": "Put the cup on the right side.", "setup": BASE,
     "expect": {"cup": "right"}, "answer_any": ["杯", "cup", "Cup"]},
    {"id": "h_near_robot", "task": "把杯子放在機器人附近", "setup": {"cup": (0.50, 0.55), "bottle": (0.55, 0.30)},
     "expect": {"cup": "near_robot"}, "answer_all": ["杯"]},
    {"id": "h_nudge_left", "task": "幫我把瓶子挪到左邊去", "setup": {"cup": (0.55, 0.30), "bottle": (0.45, 0.47)},
     "expect": {"bottle": "left"}, "answer_all": ["瓶"]},
    {"id": "h_just_centre", "task": "杯子放中間就好", "setup": {"cup": (0.55, 0.30), "bottle": (0.38, 0.62)},
     "expect": {"cup": "center"}, "answer_all": ["杯"]},
    # B. questions: nothing may move
    {"id": "h_how_many", "task": "桌上現在有幾樣東西？", "setup": BASE, "expect": {},
     "answer_any": ["2", "兩", "二"]},
    {"id": "h_where_bottle", "task": "瓶子在什麼位置？", "setup": BASE, "expect": {},
     "answer_all": ["瓶"], "answer_coords": "bottle"},
    {"id": "h_right_free", "task": "右邊有東西嗎？", "setup": {"cup": RIGHT, "bottle": (0.38, 0.62)},
     "expect": {}, "answer_all": ["杯", "有"]},
    {"id": "h_ask_first", "task": "現在可以把瓶子放到右邊嗎？先不要動，告訴我就好",
     "setup": {"cup": RIGHT, "bottle": (0.38, 0.62)}, "expect": {}, "answer_all": ["杯"],
     "answer_any": BLOCKED},
    # C. constraints and negation
    {"id": "h_dont_touch", "task": "把杯子放到中間，但不要碰瓶子",
     "setup": {"cup": (0.55, 0.30), "bottle": CENTER}, "expect": {}, "answer_all": ["瓶"],
     "answer_any": BLOCKED},
    {"id": "h_english_keep", "task": "Don't move the bottle. Put the cup on the left.",
     "setup": {"cup": (0.55, 0.30), "bottle": LEFT}, "expect": {},
     "answer_any": BLOCKED + ["occupied", "blocked", "cannot", "can't"]},
    {"id": "h_stay", "task": "瓶子留在原地，杯子移到右邊", "setup": BASE,
     "expect": {"cup": "right"}, "answer_all": ["杯"]},
    {"id": "h_only_cup", "task": "除了杯子以外，什麼都不要動。杯子放到靠近機器人的地方",
     "setup": {"cup": (0.50, 0.55), "bottle": (0.55, 0.30)}, "expect": {"cup": "near_robot"},
     "answer_all": ["杯"]},
    # D. several steps
    {"id": "h_then", "task": "先把杯子移到右邊，然後瓶子移到中間",
     "setup": {"cup": (0.38, 0.62), "bottle": (0.32, 0.36)}, "expect": {"cup": "right", "bottle": "center"},
     "answer_all": ["杯", "瓶"]},
    {"id": "h_both_left", "task": "把兩個東西都移到左邊", "setup": {"cup": (0.55, 0.30), "bottle": CENTER},
     "expect": {}, "one_in": ("left", ["cup", "bottle"]),
     "answer_any": ["空間", "放不下", "占", "佔", "無法", "沒辦法", "不能", "只能"]},
    {"id": "h_swap", "task": "把杯子放到右邊，瓶子放到左邊", "setup": {"cup": LEFT, "bottle": RIGHT},
     "expect": {"cup": "right", "bottle": "left"}, "answer_all": ["杯", "瓶"]},
    {"id": "h_move_then_ask", "task": "把瓶子放到右邊，然後告訴我杯子在哪", "setup": BASE,
     "expect": {"bottle": "right"}, "answer_all": ["杯"], "answer_coords": "cup"},
    # E. things the arm cannot do
    {"id": "h_phone", "task": "把手機放到左邊", "setup": BASE, "expect": {},
     "answer_all": ["手機"], "answer_any": ["沒有", "找不到", "不在", "無法"]},
    {"id": "h_under_table", "task": "把杯子放到桌子底下", "setup": BASE, "expect": {},
     "answer_any": NO + ["不存在"]},
    {"id": "h_throw_away", "task": "把瓶子丟掉", "setup": BASE, "expect": {}, "answer_any": NO},
    {"id": "h_lift", "task": "把杯子舉高一點", "setup": BASE, "expect": {}, "answer_any": NO},
    # F. the user says how to clear a blocked area / two targets at once
    {"id": "h_user_clearing", "task": "杯子要放到右邊，但右邊有瓶子的話就先把瓶子移到中間",
     "setup": {"cup": (0.38, 0.62), "bottle": RIGHT}, "expect": {"cup": "right", "bottle": "center"},
     "answer_all": ["杯", "瓶"]},
    {"id": "h_two_targets", "task": "把杯子放到機器人旁邊，瓶子放到中間",
     "setup": {"cup": (0.55, 0.30), "bottle": (0.38, 0.62)}, "expect": {"cup": "near_robot", "bottle": "center"},
     "answer_all": ["杯", "瓶"]},
]

# A second set, written 2026-11-27 21:25, after the fixes for the first set's
# failures and never run before those fixes were final: it checks that the
# fixes are not just tuned to the first 24 commands.
HELDOUT2 = [
    {"id": "h2_push", "task": "把那個瓶子推到中間", "setup": {"cup": (0.55, 0.30), "bottle": (0.38, 0.62)},
     "expect": {"bottle": "center"}, "answer_all": ["瓶"]},
    {"id": "h2_thanks", "task": "杯子移到左側，謝謝", "setup": BASE, "expect": {"cup": "left"}, "answer_all": ["杯"]},
    {"id": "h2_coords", "task": "可以告訴我杯子的座標嗎？", "setup": BASE, "expect": {},
     "answer_all": ["杯"], "answer_coords": "cup"},
    {"id": "h2_english", "task": "Move the bottle to the center.", "setup": {"cup": (0.38, 0.62), "bottle": (0.55, 0.30)},
     "expect": {"bottle": "center"}, "answer_any": ["瓶", "bottle", "Bottle"]},
    {"id": "h2_keep_blocked", "task": "瓶子不要動，把杯子放到中間", "setup": {"cup": (0.55, 0.30), "bottle": CENTER},
     "expect": {}, "answer_any": BLOCKED},
    {"id": "h2_dont_touch", "task": "別碰杯子，把瓶子放到右邊", "setup": {"cup": RIGHT, "bottle": (0.38, 0.62)},
     "expect": {}, "answer_any": BLOCKED},
    {"id": "h2_swap_words", "task": "把杯子跟瓶子的位置對調", "setup": {"cup": LEFT, "bottle": RIGHT},
     "expect": {"cup": "right", "bottle": "left"}, "answer_all": ["杯", "瓶"]},
    {"id": "h2_all_near", "task": "把所有東西都放到靠近機器人的地方", "setup": {"cup": (0.55, 0.30), "bottle": (0.38, 0.62)},
     "expect": {}, "one_in": ("near_robot", ["cup", "bottle"]),
     "answer_any": ["空間", "放不下", "占", "佔", "無法", "沒辦法", "不能", "只能"]},
    {"id": "h2_pencil", "task": "把鉛筆放到右邊", "setup": BASE, "expect": {},
     "answer_all": ["鉛筆"], "answer_any": ["沒有", "找不到", "不在", "無法"]},
    {"id": "h2_ceiling", "task": "把杯子放到天花板上", "setup": BASE, "expect": {}, "answer_any": NO + ["不存在"]},
    {"id": "h2_next", "task": "先把瓶子放到中間，接著把杯子放到左邊",
     "setup": {"cup": (0.55, 0.30), "bottle": (0.32, 0.36)}, "expect": {"bottle": "center", "cup": "left"},
     "answer_all": ["杯", "瓶"]},
    {"id": "h2_by_place", "task": "右邊的東西移到中間", "setup": {"cup": RIGHT, "bottle": (0.38, 0.62)},
     "expect": {"cup": "center"}, "answer_all": ["杯"]},
]
