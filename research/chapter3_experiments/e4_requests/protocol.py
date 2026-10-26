"""Fixed E4b request-copy recipe; no scientific backend imports."""
PROTOCOL_ID="E4_REQUESTS_V1"
SLOTS=(("base__R1","FULL"),("requests_2__R1","FULL"))
BUDGETS=dict(plan_s=300,post_s=60,plan_calls=2,post_calls=2)
SUPERVISION=dict(slot_wall_s=420,batch_wall_s=960,archive_only_grace_s=5)
