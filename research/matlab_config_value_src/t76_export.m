function t76_export(folder,results)
summary=cell(0,13);
for k=1:numel(results)
 r=results{k};if isempty(r),continue;end
 states=cellfun(@(x)x.status,r.thermal,'UniformOutput',false);
 raw=[];orbit=[];types={};safeRemoved=[];
 for j=1:numel(r.cuts)
  cut=r.cuts{j};raw(j)=numel(cut.excluded_rows);orbit(j)=numel(cut.excluded_orbits);types{j}=cut.kind;safeRemoved(j)=cut.safe_removed;
 end
 minraw=NaN;maxraw=NaN;minorbit=NaN;maxorbit=NaN;
 if ~isempty(raw),minraw=min(raw);maxraw=max(raw);minorbit=min(orbit);maxorbit=max(orbit);end
 summary(end+1,:)={r.id,r.status,r.checked_rows,sum(strcmp(states,'safe')),sum(strcmp(states,'violation')), ...
  sum(strcmp(states,'unresolved')),r.checked_cuts,minraw,maxraw,minorbit,maxorbit,sum(safeRemoved),r.elapsed_s}; %#ok<AGROW>
 if isempty(r.rows),continue;end
 schedules=array2table(double(r.rows));schedules.Properties.VariableNames=[cellstr(compose('choice_%d',1:8)) cellstr(compose('start_tick_%d',1:8))];
 schedules.row_id=(1:height(schedules))';schedules.energy_mJ=r.energy_J*1000;schedules.orbit_id=r.orbits;
 status=repmat("not_evaluated",height(schedules),1);lo=nan(height(schedules),2);hi=lo;at=lo;
 for j=1:numel(r.thermal),status(j)=r.thermal{j}.status;lo(j,:)=r.thermal{j}.peak_lower;hi(j,:)=r.thermal{j}.peak_upper;at(j,:)=r.thermal{j}.peak_time;end
 schedules.thermal_status=status;schedules.CPU_peak_lower=lo(:,1);schedules.CPU_peak_upper=hi(:,1);
 schedules.NPU_peak_lower=lo(:,2);schedules.NPU_peak_upper=hi(:,2);schedules.CPU_peak_time_ms=at(:,1)*1000;schedules.NPU_peak_time_ms=at(:,2)*1000;
 writetable(schedules,fullfile(folder,[r.id '_schedules.csv']));
 if ~isempty(raw)
  source=cellfun(@(x)x.source_row,r.cuts)';node=nan(numel(raw),1);ts=node;rhs=node;lhslo=node;
  coverage=false(numel(raw),size(r.rows,1));
  for j=1:numel(raw)
   cut=r.cuts{j};coverage(j,cut.excluded_rows)=true;
   if strcmp(cut.kind,'temperature_row'),node(j)=cut.row.node;ts(j)=cut.row.time_s;rhs(j)=cut.row.rhs_upper;lhslo(j)=cut.source_lhs_interval(1);end
  end
  cuts=table(source,string(types(:)),node,ts*1000,rhs,lhslo,raw(:),orbit(:),safeRemoved(:), ...
   'VariableNames',{'source_row','kind','node','time_ms','rhs_upper_C','source_lhs_lower_C','excluded_raw','excluded_orbits','safe_removed'});
  writetable(cuts,fullfile(folder,[r.id '_cuts.csv']));writematrix(coverage,fullfile(folder,[r.id '_cut_coverage.csv']));
  f=figure('Visible','off','Color','white');imagesc(coverage);xlabel('Canonical schedule index');ylabel('Source violating schedule index');
  title('Fixed-time row exclusion (offline diagnostic)');colorbar;exportgraphics(f,fullfile(folder,[r.id '_coverage.png']),'Resolution',180);close(f);
 end
end
t=cell2table(summary,'VariableNames',{'case_id','status','arrangements','safe','violation','unresolved','cuts', ...
 'min_excluded_raw','max_excluded_raw','min_excluded_orbits','max_excluded_orbits','safe_removed','elapsed_s'});
writetable(t,fullfile(folder,'summary.csv'));disp(t);
end
