"""Fixed E4a deadline recipe; no scientific backend imports."""
PROTOCOL_ID="E4_DEADLINE_V1"
SLOTS=(("beta_1.0__R1","FULL"),("base__R1","FULL"),("beta_1.6__R1","FULL"))
BUDGETS=dict(plan_s=300,post_s=60,plan_calls=3,post_calls=3)
SUPERVISION=dict(slot_wall_s=420,batch_wall_s=1380,archive_only_grace_s=5)
