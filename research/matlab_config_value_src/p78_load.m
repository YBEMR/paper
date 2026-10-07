function [trials,rules,base]=p78_load(design)
root=fileparts(fileparts(design));source=fullfile(root,'research','stage53_design');
inputs=jsondecode(fileread(fullfile(design,'inputs_v1.json')));
rules=jsondecode(fileread(fullfile(design,'rules_v1.json')));
manifest=jsondecode(fileread(fullfile(design,'freeze_manifest.json')));
for name={'inputs_v1','rules_v1','protected_before'}
 p=fullfile(design,[name{1} '.json']);z=c44_audit({p});
 assert(strcmpi(z.sha256,manifest.([name{1} '_json'])),'p78:freeze','Frozen file changed');
end
sh=c44_audit({fullfile(source,'inputs_v1.json'),fullfile(source,'rules_v1.json')});
assert(strcmpi(sh(1).sha256,inputs.source_input_sha256) && strcmpi(sh(2).sha256,inputs.source_rules_sha256));
[base,~]=s55_load(source);
trials=struct('id',{},'cohort',{},'case',{},'thermal',{},'base_id',{},'initial_C',{});
for k=1:numel(inputs.cases)
 z=inputs.cases(k);b=base(strcmp({base.id},z.base_id));assert(isscalar(b));
 c=b.case;c.id=z.id;h=b.thermal;h.initial=z.initial_C(:)';
 t=struct('id',z.id,'cohort',z.cohort,'case',c,'thermal',h,'base_id',z.base_id,'initial_C',h.initial);
 cc=c;cc.id=b.case.id;hh=h;hh.initial=b.thermal.initial;
 assert(isequaln(cc,b.case) && isequaln(hh,b.thermal),'p78:input','Only ID/initial may change');
 assert(all(h.initial<h.limit) && h.initial(1)==h.initial(2));
 trials(end+1)=t; %#ok<AGROW>
end
assert(numel(trials)==17 && numel(rules.calls)==66 && rules.budget_s==60);
end
