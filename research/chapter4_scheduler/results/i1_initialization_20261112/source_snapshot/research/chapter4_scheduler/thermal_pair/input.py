"""Derive only exogenous entry temperatures from the intact C01 contract."""
from copy import deepcopy
from fractions import Fraction as F
from research.chapter4_scheduler.c01.input import load_c01,SOURCE,SOURCE_SHA256
from research.chapter4_scheduler.mechanism_check.run import digest

BASE_CONFIG="15ca987441165a0e994ddbe073874ef23c76ee6ec26d4eecfa41b436ca0c6c83"
BASE_INSTANCE="b292ced36fec69f4aa97c39edce6df7df58a27b9cec85135ad77a7e0cf4b8f48"
TEMPERATURES=("50","78")

def validate_pair(config,instance,temperature):
    if type(temperature) is not str or temperature not in TEMPERATURES:
        raise ValueError("ONLY_PREDECLARED50_78_PAIR")
    c,i=deepcopy(config),deepcopy(instance)
    if c['defaults']['initial_temperature_degC']!=temperature:raise ValueError('CONFIG_ENTRY_MISMATCH')
    c['defaults']['initial_temperature_degC']='50'
    for scene in i['scenarios']:
        if scene['entry']['temperature_degC']!=[temperature]*4:raise ValueError('SCENE_ENTRY_MISMATCH')
        if scene['maximum_temperature_degC']!=['80']*4:raise ValueError('LIMIT_CHANGED')
        scene['entry']['temperature_degC']=['50']*4
    if (digest(c),digest(i))!=(BASE_CONFIG,BASE_INSTANCE):raise ValueError('NON_TEMPERATURE_INPUT_CHANGED')
    platform=instance['platform'];lo,hi=map(F,platform['power_model_temperature_range_degC'])
    if not lo<=F(temperature)<F(80)<=hi:raise ValueError('ENTRY_OR_LIMIT_OUTSIDE_MODEL')
    capacities=list(map(F,platform['heat_capacity_J_per_K']))
    conductance=[list(map(F,row)) for row in platform['conductance_W_per_K']]
    if any(c<=0 for c in capacities):raise ValueError('NONPOSITIVE_HEAT_CAPACITY')
    for j,row in enumerate(conductance):
        if row[j]<=0 or sum(row)<=0:raise ValueError('UNGROUNDED_CONDUCTANCE')
        for k,value in enumerate(row):
            if value!=conductance[k][j] or (j!=k and value>0):raise ValueError('NONPASSIVE_CONDUCTANCE')
    return True

def derive(config,instance,temperature):
    if (digest(config),digest(instance))!=(BASE_CONFIG,BASE_INSTANCE):raise ValueError('ORIGINAL_C01_REQUIRED')
    if type(temperature) is not str or temperature not in TEMPERATURES:raise ValueError('ONLY_PREDECLARED50_78_PAIR')
    c,i=deepcopy(config),deepcopy(instance)
    c['defaults']['initial_temperature_degC']=temperature
    for scene in i['scenarios']:scene['entry']['temperature_degC']=[temperature]*4
    validate_pair(c,i,temperature)
    return c,i

def load_pair(budget,temperature):
    # The original loader validates original provenance and fixed50C contract.
    # The fresh derived pair has its own hashes, never forged old provenance.
    config,instance=load_c01(budget)
    budget.check();pair=derive(config,instance,temperature);budget.check()
    return pair
