"""Exact random-order replay: PCG is not used; Python MT19937 draws are encoded by opcode."""
import base64
import random

streams=[]


class Random(random.Random):
    def __init__(self,seed):
        super().__init__(seed)
        self.initial_seed=seed
        self.ops=bytearray()
        streams.append(self)
    def random(self):
        self.ops.append(0)
        return super().random()
    def getrandbits(self,k):
        if not 0<k<256: raise ValueError("opcode width")
        self.ops.append(k)
        return super().getrandbits(k)


def records():
    return [dict(seed=r.initial_seed,draw_count=len(r.ops),opcodes=base64.b64encode(r.ops).decode("ascii"))
            for r in streams]
