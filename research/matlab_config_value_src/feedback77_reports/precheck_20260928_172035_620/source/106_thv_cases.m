function trials = thv_cases()
% Frozen abstract thermal protocol; original cv_cases remains unchanged.
all=cv_cases(); ids={'R1_alpha_02','R1_alpha_10','R2_above_tight'};
base=struct('ambient',25,'limit',[80 80],'g_env',[.05 .05], ...
    'g',.025,'capacity',[.0025 .0025],'initial',[30 30], ...
    'band',1e-6,'grid',.001,'budget_s',60,'provenance','abstract_not_calibrated');
trials=struct('id',{},'case',{},'thermal',{},'role',{});
labels={'cold','warm','hot'}; temps=[30 70 78];
for i=1:3
    c=all(strcmp({all.id},ids{i}));
    for j=1:3
        h=base; h.initial=[temps(j) temps(j)];
        trials(end+1)=struct('id',[c.id '_' labels{j} '_g025_dt1'], ...
            'case',c,'thermal',h,'role','main');
    end
end
for i=1:3
    c=all(strcmp({all.id},ids{i})); h=base; h.initial=[78 78]; h.g=0;
    trials(end+1)=struct('id',[c.id '_hot_g0_dt1'],'case',c,'thermal',h,'role','coupling_control');
end
for i=1:3
    c=all(strcmp({all.id},ids{i})); h=base; h.initial=[78 78]; h.grid=.0005;
    trials(end+1)=struct('id',[c.id '_hot_g025_dt05'],'case',c,'thermal',h,'role','grid_refinement');
end
end
