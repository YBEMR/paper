function summary=c44_export(folder,trials,runs,refs)
rows={}; timeline={}; events={}; reference={}; mode_names={'LL','LH','HL','HH'};
for k=1:numel(trials)
    tr=trials(k); c=tr.case; h=tr.thermal; ref=refs{k};
    reference(end+1,:)={tr.id,tr.role,ref.status,ref.library_count,ref.noheat_energy*1000, ...
        joincodes(ref.noheat_modes),ref.lower_J*1000,ref.upper_J*1000,ref.energy_exact, ...
        joincodes(ref.optimal_modes),ref.optimal_modes_complete,ref.elapsed_s,ref.divergence.status,ref.divergence.time*1000}; %#ok<AGROW>
    for j=1:2
        r=runs{k,j}; s=r.schedule; energy=nan; peaks=[nan nan]; safe='not_evaluated'; gap=nan; valid=false;
        if strcmp(r.status,'complete')
            v=c44_validate(c,s); e=cv_energy(c,s); z=c44_thermal(c,s,h);
            energy=e.integral*1000; peaks=z.peak; safe=z.status; valid=v.feasible && strcmp(safe,'safe');
            if valid && ref.energy_exact, gap=energy-ref.upper_J*1000; end
        end
        reject=sum([r.events.rejected]); waits=sum(arrayfun(@(x)x.selected>0&&isempty(x.started),r.events));
        modes='--'; if all(isfinite(s.modes)), modes=mode_names{2*(s.modes(1)-1)+s.modes(2)}; end
        rows(end+1,:)={tr.id,tr.role,r.version,r.status,valid,modes,s.finish(3)*1000,s.finish(4)*1000, ...
            energy,safe,peaks(1),peaks(2),gap,reject,waits,r.thermal_evaluations,r.library_count,r.elapsed_s}; %#ok<AGROW>
        for stage=1:4
            timeline(end+1,:)={tr.id,r.version,stage,s.unit(stage),s.start(stage)*1000,s.finish(stage)*1000,s.duration(stage)*1000,s.increment(stage)}; %#ok<AGROW>
        end
        for v=r.events
            events(end+1,:)={tr.id,r.version,v.time*1000,v.candidates,v.tested,v.rejected,v.unresolved,v.selected,mat2str(v.started),mat2str(v.prefix.modes)}; %#ok<AGROW>
        end
        writejson(fullfile(folder,[tr.id '_' r.version '_events.json']),r);
    end
end
summary=cell2table(rows,'VariableNames',{'case_id','role','version','status','valid_solution','modes','completion_A_ms','completion_B_ms','energy_mJ','thermal','peak_CPU_C','peak_NPU_C','gap_mJ','thermal_rejections','wait_ticks','thermal_calls','legal_schedules','elapsed_s'});
writetable(summary,fullfile(folder,'summary.csv'));
writetable(cell2table(reference,'VariableNames',{'case_id','role','status','legal_schedules','noheat_mJ','noheat_modes','lower_mJ','upper_mJ','energy_exact','optimal_modes','mode_set_complete','elapsed_s','divergence_status','divergence_ms'}),fullfile(folder,'reference.csv'));
writetable(cell2table(timeline,'VariableNames',{'case_id','version','stage','unit','start_ms','finish_ms','duration_ms','increment_W'}),fullfile(folder,'schedules.csv'));
writetable(cell2table(events,'VariableNames',{'case_id','version','time_ms','candidates','tested','rejected','unresolved','selected_rank','started_stages','modes'}),fullfile(folder,'decisions.csv'));
writejson(fullfile(folder,'references.json'),refs);
    function v=joincodes(ix)
        if isempty(ix), v=''; else, v=strjoin(mode_names(ix),','); end
    end
end
function writejson(path,value)
fid=fopen(path,'w','n','UTF-8'); assert(fid>=0); g=onCleanup(@()fclose(fid)); %#ok<NASGU>
fprintf(fid,'%s',jsonencode(value,'PrettyPrint',true));
end
