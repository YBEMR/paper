function b68_export(folder)
a=load(fullfile(folder,'results.mat'));rows=struct([]);checkrows=struct([]);k=0;z=0;
for i=1:10
 c=a.trials(i).case;h=a.trials(i).thermal;
 fig=figure('Visible','off','Position',[100 100 980 480]);tiledlayout(1,2);
 nexttile;hold on;title([a.trials(i).id ' safe energy'],'Interpreter','none');xlabel('method elapsed / s');ylabel('mJ');
 for j=1:2
  r=a.results{i,j};safe=false;peak=[NaN NaN];
  if ~isempty(r.schedule)
   v=s55_validate(c,r.schedule);assert(v.feasible);e=s55_energy(c,r.schedule);th=b64_thermal(c,r.schedule,h);safe=strcmp(th.status,'safe');peak=th.peak_upper;
   assert(safe && e.error_J<1e-12 && abs(e.sum_J-r.upper_J)<1e-12);
   z=z+1;checkrows(z)=struct('case_id',c.id,'method',r.method,'passed',true,'note','Complete legality, energy twice, continuous thermal envelope');
   s=r.schedule;T=table(c.stage_id',s.unit',s.mode',s.start',s.finish',s.duration',s.increment','VariableNames',{'stage','unit','mode','start_s','finish_s','duration_s','increment_W'});writetable(T,fullfile(folder,sprintf('schedule_%02d_%02d.csv',i,j)));
  end
  k=k+1;sb=NaN;calls=r.stats.thermal_calls;cuts=0;nr=0;if j==2,sb=r.solver_bound_J;cuts=r.stats.cuts;nr=r.stats.rounds;end
  rows(k)=struct('case_id',c.id,'cohort',a.trials(i).cohort,'method',r.method,'status',r.status,'safe',safe, ...
   'energy_mJ',r.upper_J*1000,'certified_lower_mJ',r.lower_J*1000,'common_L0_mJ',r.common_L0_J*1000, ...
   'solver_bound_mJ',sb*1000,'independent_optimal',r.optimal_value_proved,'independent_infeasible',r.grid_infeasible_proved, ...
   'elapsed_s',r.elapsed_s,'first_safe_s',r.first_safe_s,'thermal_calls',calls,'cuts',cuts,'rounds',nr,'cpu_peak_upper_C',peak(1),'npu_peak_upper_C',peak(2));
  bt=r.bound_trace;scale=1/16; % bound traces use integer energy units -> mJ
  stairs(bt(:,1),bt(:,3)*scale,'DisplayName',r.method);
  writematrix(bt,fullfile(folder,sprintf('bounds_units_%02d_%02d.csv',i,j)));
  if j==2,writematrix(r.solver_trace,fullfile(folder,sprintf('solver_trace_units_%02d.csv',i)));end
 end
 legend('Location','best','Interpreter','none');nexttile;hold on;title('Certified and solver-reported bounds');xlabel('method elapsed / s');ylabel('mJ');
 r=a.results{i,1};stairs(r.bound_trace(:,1),r.bound_trace(:,2)/16,'DisplayName','no repair certified');
 r=a.results{i,2};stairs(r.bound_trace(:,1),r.bound_trace(:,2)/16,'DisplayName','MILP L0');if ~isempty(r.solver_trace),plot(r.solver_trace(:,1),r.solver_trace(:,3)/16,':','DisplayName','MILP reported');end
 legend('Location','best');exportgraphics(fig,fullfile(folder,sprintf('bounds_%02d.png',i)));close(fig);
end
writetable(struct2table(rows),fullfile(folder,'summary.csv'));writetable(struct2table(checkrows),fullfile(folder,'postchecks.csv'));
end
