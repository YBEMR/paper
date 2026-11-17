"""Build the identifiability ledger without imputing missing hardware values."""
import csv,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
contract_path=ROOT/'input_evidence_contract.json'
contract=json.loads(contract_path.read_text(encoding='utf-8'))
sources=[
 {'id':'S1','title':'LoudVA author artifact','revision':'2b4b15efa5231d445b85d500ea5ef51d381a64c3','url':'https://github.com/iloudaros/LoudVA/tree/2b4b15efa5231d445b85d500ea5ef51d381a64c3','scope':'81 fixed files inspected in preceding audit; descriptive AGX data, no single-batch/thermal/DPM calibration','prior_audit_commit':'7bd4e7f85cb36b59d69e1a68ecc568733f754ff8'},
 {'id':'S2','title':'NVIDIA Jetson AGX Xavier Thermal Design Guide TDG-08981-001_v1.0','date':'2018-10','url':'https://www.diamondsystems.com/files/binaries/Jetson_AGX_Xavier_Thermal_Design_Guide_v1.0.pdf','scope':'NVIDIA-authored original document hosted by carrier vendor; targeted Section3.1.1, Fig3-1 and Table3-1 (printed pages8-9, PDF indexes11-12). Web PDF text checked; no local PDF structural validation claimed.'},
 {'id':'S3','title':'NVIDIA Jetson Linux R35.6.0 power/thermal guide','url':'https://docs.nvidia.com/jetson/archives/r35.6.0/DeveloperGuide/SD/PlatformPowerAndPerformance/JetsonXavierNxSeriesAndJetsonAgxXavierSeries.html','scope':'Active power-gating, SC7 distinction, six AGX rails, SOC_THERM precision margin; not a measured transient calibration'},
 {'id':'S4','title':'Balancing Energy Efficiency and Real-Time Performance in GPU Scheduling (sBEET, RTSS2021)','url':'https://intra.engr.ucr.edu/~hyoseung/pdf/rtss2021_sBEET.pdf','scope':'Author manuscript targeted Sections II-A, IV-A, V-A: GPU-rail-only energy, fixed670MHz,10-minute average power characterization, temperature impact not modeled in that experiment. Not same Inception workload/board setup.'},
 {'id':'S5','title':'Previous synthetic mechanism screen','url':'https://github.com/YBEMR/paper/blob/a1c2c1f4829d7ae58c3fbf73da765b67381e916e/research/direction_screening_20261114/parameters.json','scope':'All dynamic simulation numerical values originate here and declared perturbations, not S1-S4 measured coefficients'},
 {'id':'S6','title':'Previous same-platform data audit','url':'https://github.com/YBEMR/paper/blob/7bd4e7f85cb36b59d69e1a68ecc568733f754ff8/research/b_parameter_audit_20261114/REPORT.md','scope':'BatchDVFS P40 excluded from AGX numerical calibration; Orin/NX calibration coefficients not transferred'}]
records=[]
def add(parameter,unit,identified_value,status,source,limitation,simulation_role):
    records.append(dict(parameter=parameter,unit=unit,identified_value=identified_value,status=status,source=source,limitation=limitation,simulation_role=simulation_role))
add('GPU_frequency_menu','MHz',[114.75,216.75,318.75,420.75,522.75,624.75,675.75,828.75,905.25,1032.75,1198.5,1236.75,1338.75,1377.],'OBSERVED_CONFIGURATION','S1','Same AGX artifact; runtime clocks may differ','Not used to infer synthetic GPU frequency')
add('concurrency_1_server_latency','ms',[27.193,267.158],'CONDITIONAL_DESCRIPTIVE_RANGE','S1','Includes queue and transfer/compute stages; range across frequencies, not uncertainty interval','Not substituted for single-batch duration')
add('concurrency_1_2_six_rail_power','W',[5.64039,26.7909],'CONDITIONAL_DESCRIPTIVE_RANGE','S1','Six-rail sum; not GPU dynamic power or calibrated system input','Not substituted for synthetic dynamic power')
add('SoC_to_TTP_thermal_resistance_balanced','K/W',.35,'MANUFACTURER_CONDITIONAL_TYPICAL','S2 Table3-1','Balanced load; not lower confidence bound or CPU/GPU-to-ambient coefficient','Physical boundary only; NOT inserted into RC matrix')
add('SoC_to_TTP_thermal_resistance_unbalanced','K/W',.65,'MANUFACTURER_CONDITIONAL_TYPICAL','S2 Table3-1','Concentrated load; not upper confidence bound; workload dependent','Physical boundary only; NOT inserted into RC matrix')
add('junction_to_board_thermal_resistance','K/W',5.5,'MANUFACTURER_CONDITIONAL','S2 Table3-1 note3','For commercial CFD two-resistor module representation; not CPU-GPU mutual thermal resistance','Physical boundary only')
add('temperature_sensor_precision_margin','C',.5,'DOCUMENTED_SENSOR_CHARACTERISTIC','S3 SOC_THERM','Not the total uncertainty of a power/temperature synchronized inference trace','Observation perturbations +/-0.5 and +/-2C remain explicit scenarios')
for key in contract['unidentified_parameters']:
    add(key,'see parameter name',None,'UNIDENTIFIED_FOR_TARGET_ACTION_MODEL','S1/S3/S4/S6','Same-model, same-runtime and matched-state identification not closed','Synthetic anchor/declared perturbation or symbolic variable only; empirical value stays null')
add('complete_system_unmodeled_extra_power','W',None,'UNIDENTIFIED','S1/S6','External peripherals/DRAM/monitoring not calibrated by six-rail table','Abstract external_base=0.3W remains synthetic; extra overhead budget reported')
ledger={'date':'2026-11-14','sources':sources,'parameters':records,'not_a_calibrated_AGX_model':True,'prior_contract_sha256':hashlib.sha256(contract_path.read_bytes()).hexdigest()}
(ROOT/'physical_evidence.json').write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with (ROOT/'parameter_identifiability.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader()
    for r in records:w.writerow({**r,'identified_value':json.dumps(r['identified_value'],ensure_ascii=False)})
print(json.dumps({'sources':len(sources),'parameters':len(records),'unknown_parameters':sum(r['identified_value'] is None for r in records)}))
