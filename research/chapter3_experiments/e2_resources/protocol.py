"""Fixed E2 recipe only; no search, scoring or physical imports."""
PROTOCOL_ID = 'E2_RESOURCES_V1'
# Immutable recipe. protocol_slots returns a fresh mutable view to callers.
SLOTS = (("resources_CPU__R1", "FULL"),
         ("resources_CPU_GPU__R1", "FULL"),
         ("resources_CPU_NPU__R1", "FULL"),
         ("base__R1", "FULL"))
