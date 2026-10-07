function [trials,rules]=s55_load(design)
% Frozen structure/mode data only. No expected result or reference input.
a=jsondecode(fileread(fullfile(design,'inputs_v1.json')));
rules=jsondecode(fileread(fullfile(design,'rules_v1.json')));
paths={fullfile(design,'inputs_v1.json'),fullfile(design,'rules_v1.json')};
hash=c44_audit(paths);
assert(strcmpi(hash(1).sha256,'cb76929032f3ee457df95200af6e106aa4fdce97760790086aed74d04aace1cd'));
assert(strcmpi(hash(2).sha256,'bda369552628a36e6f39112e02f34f6dc774683392ab242493aa94a297b85a78'));
trials=struct('id',{},'cohort',{},'case',{},'thermal',{}); unitnames={'C1','C2','N'}; moden={'L','H','FIXED'};
for k=1:numel(a.cases)
    z=a.cases(k); p=a.packages(strcmp({a.packages.package_id},z.package_id));
    c=struct('id',z.case_id,'cohort',z.cohort,'n',8,'request',[1 1 1 1 2 2 2 2], ...
        'pred',{{[],1,2,3,[],5,6,7}},'terminal',[4 8],'stage_id',{{}},'options',{{}}, ...
        'release',[z.requests.release_s],'deadline',[z.requests.deadline_s], ...
        'grid',a.system.start_grid_s,'window',a.system.window_s, ...
        'idle_cpu',a.system.idle_cpu_total_W,'idle_npu',a.system.idle_npu_W, ...
        'external',a.system.external_W,'unit_kind',[1 1 2],'domain',[1 1 0], ...
        'time_tol',rules.tolerance.time_s,'energy_abs_tol',rules.tolerance.energy_absolute_J, ...
        'energy_rel_tol',rules.tolerance.energy_relative,'budget_s',rules.budget.seconds_per_case_per_method);
    for i=1:8
        typ=sprintf('S%d',mod(i-1,4)); req='A'+(i>4);
        c.stage_id{i}=sprintf('%c.%s',req,typ);
        mm=p.modes(strcmp({p.modes.stage_type},typ)); opts=zeros(numel(mm),4);
        for j=1:numel(mm)
            opts(j,:)=[find(strcmp(unitnames,mm(j).unit_id)),find(strcmp(moden,mm(j).frequency_id)), ...
                mm(j).duration_s,mm(j).active_increment_W];
        end
        c.options{i}=sortrows(opts,[1 2]);
    end
    hh=a.thermal;
    h=struct('ambient',hh.ambient_C,'limit',hh.limit_C(:)', ...
        'g_env',hh.env_conductance_W_per_K(:)','g',hh.coupling_W_per_K, ...
        'capacity',hh.capacity_J_per_K(:)','initial',z.initial_C(:)', ...
        'band',rules.tolerance.temperature_C);
    assert(c.n==8 && all(cellfun(@(x)all(isfinite(x(:))) && all(x(:,3)>0) && all(x(:,4)>=0),c.options)));
    assert(all(c.deadline<=c.window) && all(c.release<c.deadline));
    trials(k)=struct('id',c.id,'cohort',c.cohort,'case',c,'thermal',h); %#ok<AGROW>
end
assert(numel(trials)==10);
end
