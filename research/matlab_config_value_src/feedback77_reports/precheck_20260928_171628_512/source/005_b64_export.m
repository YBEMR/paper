function b64_export(folder)
% Post-run independent checks; never performs schedule search or repairs.
a=load(fullfile(folder,'results.mat'));rows={};checks={};
for i=1:numel(a.trials)
 c=a.trials(i).case;h=a.trials(i).thermal;
 fig=figure('Visible','off');hold on;leg={};
 for j=1:numel(a.methods)
  r=a.results{i,j};if isempty(r),continue;end
  complete=~isempty(r.schedule) && all(isfinite(r.schedule.start));legal=false;safe=false;pk=[NaN NaN];C=[NaN NaN];E=NaN;
  if complete
   v=s55_validate(c,r.schedule);legal=v.feasible;
   if legal
    e=s55_energy(c,r.schedule);z=b64_thermal(c,r.schedule,h);safe=strcmp(z.status,'safe');pk=z.peak;C=v.completion;E=e.sum_J;
    checks(end+1,:)={c.id,a.methods{j},'energy_double',e.error_J<=c.energy_abs_tol}; %#ok<AGROW>
    checks(end+1,:)={c.id,a.methods{j},'thermal_enclosure',all(pk>=z.peak_lower-1e-9) && all(pk<=z.peak_upper+1e-9)};
   end
   checks(end+1,:)={c.id,a.methods{j},'complete_legal',legal};
   if j<=4 || strcmp(r.status,'complete_safe')
    checks(end+1,:)={c.id,a.methods{j},'claimed_safe',safe};
   end
  end
  p=0;q=0;calls=0;rep=0;success=0;cache=0;first=NaN;g=NaN;sc=NaN;qu=NaN;th=NaN;re=NaN;val=NaN;
  if j<=4
   p=r.stats.popped;q=r.stats.max_queue;calls=r.stats.thermal_calls;rep=r.stats.repair_trials;success=r.stats.repair_safe;cache=r.stats.cache_hits;first=r.first_safe_s;
   g=r.cost_s.generation;sc=r.cost_s.scoring;qu=r.cost_s.queue;th=r.cost_s.thermal;re=r.cost_s.repair;val=r.cost_s.validation;
   trace=r.bound_trace;trace(:,2:3)=trace(:,2:3)/16000*1000;
   writematrix(trace,fullfile(folder,sprintf('bounds_%02d_%s.csv',i,a.methods{j})));
   plot(trace(:,1),trace(:,3),'-');leg{end+1}=[a.methods{j} ' U']; %#ok<AGROW>
   plot(trace(:,1),trace(:,2),'--');leg{end+1}=[a.methods{j} ' L']; %#ok<AGROW>
   writematrix(r.events,fullfile(folder,sprintf('events_%02d_%s.csv',i,a.methods{j})));
  else,calls=r.thermal_calls;end
  rows(end+1,:)={c.id,a.trials(i).cohort,a.methods{j},r.status,complete,legal,safe,E*1000, ...
   r.lower_J*1000,r.upper_J*1000,r.optimal_value_proved,r.elapsed_s,first,C(1)*1000,C(2)*1000, ...
   pk(1),pk(2),p,q,calls,rep,success,cache,g,sc,qu,th,re,val}; %#ok<AGROW>
  if complete && legal
   s=r.schedule;T=table(c.stage_id',s.unit',s.mode',s.start'*1000,s.finish'*1000,s.increment', ...
    'VariableNames',{'stage','unit','mode','start_ms','finish_ms','increment_W'});
   writetable(T,fullfile(folder,sprintf('schedule_%02d_%s.csv',i,a.methods{j})));
  end
 end
 xlabel('elapsed seconds');ylabel('energy (mJ)');title(c.id,'Interpreter','none');grid on;
 if ~isempty(leg),legend(leg,'Interpreter','none','Location','best');end
 saveas(fig,fullfile(folder,sprintf('bounds_%02d.png',i)));close(fig);
end
names={'case_id','cohort','method','status','complete','legal','safe','energy_mJ','lower_mJ','upper_mJ', ...
 'optimal_value_proved','elapsed_s','first_safe_s','A_finish_ms','B_finish_ms','CPU_peak_C','NPU_peak_C', ...
 'popped','max_queue','thermal_calls','repair_trials','repair_success','cache_hits','generation_s','scoring_s', ...
 'queue_s','thermal_s','repair_s','validation_s'};
summary=cell2table(rows,'VariableNames',names);writetable(summary,fullfile(folder,'summary.csv'));
post=cell2table(checks,'VariableNames',{'case_id','method','check','passed'});writetable(post,fullfile(folder,'postchecks.csv'));
save(fullfile(folder,'postprocess.mat'),'summary','post');assert(all(post.passed),'Independent check failed');
fprintf('POSTCHECK %d/%d\n',sum(post.passed),height(post));
end
