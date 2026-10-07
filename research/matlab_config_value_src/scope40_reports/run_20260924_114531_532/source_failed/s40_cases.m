function trials=s40_cases()
% Frozen 39/40 protocol. No measured hardware parameters.
old=thv_cases(); trials=struct([]); packs={'L3_Q','L3_S'};
ids={'R1_alpha_02','R1_alpha_10'};
for p=1:2
    base=old(find(arrayfun(@(t)strcmp(t.case.id,ids{p}),old),1));
    for rho=[1 1.5 2 3 4 6]
        for margin=[.05 .25 .5 .75 1]
            t=base; t.role='scope40'; t.case.deadline=rho*[.007 .007];
            t.thermal.initial=t.thermal.limit-margin*(t.thermal.limit-t.thermal.ambient);
            t.id=sprintf('%s_r%02d_h%03d',packs{p},round(10*rho),round(100*margin));
            t.package=packs{p}; t.rho=rho; t.margin=margin;
            trials(end+1)=t; %#ok<AGROW>
        end
    end
end
end
