"""Fixed original/fallback pair, identical scientific packets."""
PROTOCOL_ID='E4_DEADLINE_FALLBACK_V1'
PROBLEM_ID='requests_2__R1'
SLOTS=((PROBLEM_ID,'FULL'),(PROBLEM_ID,'FULL'))
METHODS=('ORIGINAL_HEFT','DEADLINE_FALLBACK')
BUDGETS=dict(plan_s=300,post_s=60,plan_calls=2,post_calls=2)
SUPERVISION=dict(slot_wall_s=420,batch_wall_s=960,archive_only_grace_s=5)
