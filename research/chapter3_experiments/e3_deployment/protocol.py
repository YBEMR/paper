"""Fixed E3 two-arm recipe; no scientific backend imports."""
PROTOCOL_ID='E3_DEPLOYMENT_V1'
SHARED_ID='base__R1'
LOCAL_ID='base__R1__E3_SCENE_LOCAL_A'
SLOTS=((SHARED_ID,'FULL'),(LOCAL_ID,'FULL'))
BUDGETS=dict(plan_s=300,post_s=60,plan_calls=2,post_calls=2)
SUPERVISION=dict(slot_wall_s=420,batch_wall_s=960,archive_only_grace_s=5)
