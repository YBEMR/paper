function f77_export(folder)
% Read-only postcheck/export of stored no-good and thermal-row MILP results.
% No solver, enumeration, schedule repair, or timing offset is applied here.
a=load(fullfile(folder,'results.mat'));
assert(isfield(a,'trials') && isfield(a,'results') && isfield(a,'methods'), ...
 'f77:exportInput','results.mat must contain trials, results, and methods');
methods=cellstr(string(a.methods));methods=methods(:)';
assert(isequal(methods,{'no_good','thermal_row'}), ...
 'f77:exportInput','Expected method order: no_good, thermal_row');
assert(iscell(a.results) && isequal(size(a.results),[numel(a.trials) 2]), ...
 'f77:exportInput','results must have one row per trial and two method columns');
summaryRows={};checkRows={};costRows={};entry=0;
for i=1:numel(a.trials)
 tr=a.trials(i);c=tr.case;h=tr.thermal;
 for j=1:2
  r=a.results{i,j};method=methods{j};
  assert(isstruct(r) && isscalar(r) && isfield(r,'schedule'), ...
   'f77:exportInput','Missing result at case %d method %d',i,j);
  U=scalarfield(r,'upper_J',NaN);L=scalarfield(r,'lower_J',NaN);
  assert(isfield(r,'common_L0_J'),'f77:exportInput','Runner must provide common_L0_J');
  L0=scalarfield(r,'common_L0_J',NaN);sb=scalarfield(r,'solver_bound_J',NaN);
  safe=false;checked=false;passed=NaN;peakLower=[NaN NaN];peakUpper=peakLower;
  energyError=NaN;upperError=NaN;verifiedEnergy=NaN;
  note='No saved safe witness; no schedule check performed';
  checkStatus='not_checked_no_witness';
  if ~isempty(r.schedule)
   checked=true;s=r.schedule;v=s55_validate(c,s);
   assert(v.feasible,'f77:postcheck','%s / %s: illegal saved schedule (%s)', ...
    tr.id,method,v.reason);
   e=s55_energy(c,s);th=b64_thermal(c,s,h);
   safe=strcmp(th.status,'safe');energyError=e.error_J;
   upperError=abs(e.sum_J-U);verifiedEnergy=e.sum_J;
   assert(safe && isfinite(U) && energyError<1e-12 && upperError<1e-12, ...
    'f77:postcheck','%s / %s: saved witness failed energy or continuous thermal check',tr.id,method);
   peakLower=reshape(th.peak_lower,1,[]);peakUpper=reshape(th.peak_upper,1,[]);
   assert(numel(peakLower)==2 && numel(peakUpper)==2,'f77:postcheck','Expected two thermal nodes');
   passed=1;checkStatus='verified_safe_witness';
   note='Complete legality, energy by sum and integral, continuous thermal envelope including tail';
   T=table(c.stage_id(:),s.choice(:),s.unit(:),s.mode(:),s.start(:),s.finish(:), ...
    s.duration(:),s.increment(:),'VariableNames', ...
    {'stage','choice','unit','mode','start_s','finish_s','duration_s','increment_W'});
   writetable(T,fullfile(folder,sprintf('schedule_%02d_%02d.csv',i,j)));
  else
   assert(~isfinite(U),'f77:postcheck','%s / %s: finite upper bound without saved witness',tr.id,method);
  end
  stats=fieldvalue(r,'stats',struct());cost=fieldvalue(r,'cost_s',struct());
  totalCuts=scalarfield(stats,'cuts',0);
  thermalRows=scalarfield(stats,'thermal_rows',0);
  if j==1,defaultNoGoods=totalCuts;else,defaultNoGoods=0;end
  noGoods=scalarfield(stats,'no_goods',defaultNoGoods);
  entry=entry+1;
  summaryRows{entry}=struct('case_id',tr.id,'cohort',tr.cohort,'method',method, ...
   'reported_method',fieldvalue(r,'method',method),'status',r.status,'safe',safe, ...
   'energy_mJ',U*1000,'certified_lower_mJ',L*1000,'common_L0_mJ',L0*1000, ...
   'solver_bound_mJ',sb*1000,'independent_optimal',logical(fieldvalue(r,'optimal_value_proved',false)), ...
   'independent_infeasible',logical(fieldvalue(r,'grid_infeasible_proved',false)), ...
   'elapsed_s',scalarfield(r,'elapsed_s',NaN),'first_safe_s',scalarfield(r,'first_safe_s',NaN), ...
   'input_setup_s',scalarfield(r,'input_setup_s',NaN), ...
   'candidates',scalarfield(stats,'candidates',0),'cache_hits',scalarfield(stats,'cache_hits',0), ...
   'thermal_calls',scalarfield(stats,'thermal_calls',0),'cuts',totalCuts, ...
   'thermal_rows',thermalRows,'no_goods',noGoods,'fallbacks',scalarfield(stats,'fallbacks',0), ...
   'duplicate_rows',scalarfield(stats,'duplicate_rows',0), ...
   'row_violations',scalarfield(stats,'row_violations',0), ...
   'row_unresolved',scalarfield(stats,'row_unresolved',0), ...
   'callbacks',scalarfield(stats,'callbacks',0),'rounds',scalarfield(stats,'rounds',0), ...
   'bound_conflicts',scalarfield(stats,'bound_conflicts',0), ...
   'cpu_peak_lower_C',peakLower(1),'cpu_peak_upper_C',peakUpper(1), ...
   'npu_peak_lower_C',peakLower(2),'npu_peak_upper_C',peakUpper(2)); %#ok<AGROW>
  checkRows{entry}=struct('case_id',tr.id,'method',method,'checked',checked, ...
   'passed',passed,'status',checkStatus,'safe',safe,'energy_mJ',verifiedEnergy*1000, ...
   'energy_sum_integral_error_J',energyError,'saved_upper_error_J',upperError, ...
   'cpu_peak_lower_C',peakLower(1),'cpu_peak_upper_C',peakUpper(1), ...
   'npu_peak_lower_C',peakLower(2),'npu_peak_upper_C',peakUpper(2),'note',note); %#ok<AGROW>
  costRows{entry}=struct('case_id',tr.id,'method',method, ...
   'elapsed_s',scalarfield(r,'elapsed_s',NaN),'input_setup_s',scalarfield(r,'input_setup_s',NaN), ...
   'build_s',scalarfield(cost,'build',0),'solver_inclusive_s',scalarfield(cost,'solver_inclusive',0), ...
   'thermal_s',scalarfield(cost,'thermal',0),'decode_s',scalarfield(cost,'decode',0), ...
   'cut_s',scalarfield(cost,'cut',0),'row_check_s',scalarfield(cost,'row_check',0), ...
   'accounting','Overlapping timers: solver_inclusive includes callbacks; do not sum columns'); %#ok<AGROW>
  bt=tracematrix(r,'bound_trace',3);st=tracematrix(r,'solver_trace',6);
  writetable(array2table(bt,'VariableNames',{'elapsed_s','certified_L0_units','safe_upper_units'}), ...
   fullfile(folder,sprintf('bounds_units_%02d_%02d.csv',i,j)));
  writetable(array2table(st,'VariableNames', ...
   {'elapsed_s','round','solver_lower_units','solver_fval_units','relative_gap','numnodes'}), ...
   fullfile(folder,sprintf('solver_trace_units_%02d_%02d.csv',i,j)));
  details=struct('case_id',tr.id,'method',method,'status',r.status, ...
   'time_basis','Stored result timestamps; exporter applies no additional input offset', ...
   'nonfinite_policy','JSON nonfinite values become null; results.mat remains authoritative', ...
   'events',{fieldvalue(r,'events',{})},'rounds',{fieldvalue(r,'rounds',{})}, ...
   'cuts',{fieldvalue(r,'cuts',{})},'unresolved',fieldvalue(r,'unresolved',[]), ...
   'callback_fields',{fieldvalue(r,'callback_fields',{})}, ...
   'message',fieldvalue(r,'message',''));
  writejson(fullfile(folder,sprintf('diagnostics_%02d_%02d.json',i,j)),details);
 end
end
assert(entry>0,'f77:exportInput','No trial results to export');
writetable(struct2table(vertcat(summaryRows{:})),fullfile(folder,'summary.csv'));
writetable(struct2table(vertcat(checkRows{:})),fullfile(folder,'postchecks.csv'));
writetable(struct2table(vertcat(costRows{:})),fullfile(folder,'cost_diagnostics.csv'));
for i=1:numel(a.trials)
 exportfigure(folder,i,a.trials(i),a.results(i,:),methods);
end
end

function exportfigure(folder,index,tr,results,methods)
% Energy-unit conversion follows the same frozen lattice as both solvers.
d=b64_data(tr.case);scale=d.energy_unit*1000;styles={'-', '--'};
fig=figure('Visible','off','Position',[100 100 1080 480]);
guard=onCleanup(@()close(fig)); %#ok<NASGU>
tiledlayout(fig,1,2);
ax1=nexttile;hold(ax1,'on');title(ax1,[tr.id ' safe energy'],'Interpreter','none');
xlabel(ax1,'method elapsed / s');ylabel(ax1,'mJ');
ax2=nexttile;hold(ax2,'on');title(ax2,'Independent L0 and solver-reported bounds');
xlabel(ax2,'method elapsed / s');ylabel(ax2,'mJ');
safeCount=0;boundCount=0;
for j=1:2
 r=results{j};bt=tracematrix(r,'bound_trace',3);st=tracematrix(r,'solver_trace',6);
 if isempty(bt)
  stairs(ax1,NaN,NaN,styles{j},'DisplayName',methods{j});
  stairs(ax2,NaN,NaN,styles{j},'DisplayName',[methods{j} ' independent L0']);
 else
  safeCount=safeCount+sum(isfinite(bt(:,3)));
  boundCount=boundCount+sum(isfinite(bt(:,2)));
  stairs(ax1,bt(:,1),finitevalues(bt(:,3)*scale),styles{j},'DisplayName',methods{j});
  stairs(ax2,bt(:,1),finitevalues(bt(:,2)*scale),styles{j}, ...
   'DisplayName',[methods{j} ' independent L0']);
 end
 if isempty(st)
  plot(ax2,NaN,NaN,':','DisplayName',[methods{j} ' solver reported']);
 else
  boundCount=boundCount+sum(isfinite(st(:,3)));
  plot(ax2,st(:,1),finitevalues(st(:,3)*scale),':', ...
   'DisplayName',[methods{j} ' solver reported']);
 end
end
if safeCount==0,text(ax1,.5,.5,'No finite safe upper bound in stored trace','Units','normalized','HorizontalAlignment','center');end
if boundCount==0,text(ax2,.5,.5,'No finite recorded bound','Units','normalized','HorizontalAlignment','center');end
legend(ax1,'Location','best','Interpreter','none');legend(ax2,'Location','best','Interpreter','none');
exportgraphics(fig,fullfile(folder,sprintf('bounds_%02d.png',index)));
end

function x=finitevalues(x)
x(~isfinite(x))=NaN; % Do not plot Inf/NaN as an attained finite bound.
end

function x=tracematrix(r,name,width)
x=fieldvalue(r,name,[]);
if isempty(x),x=zeros(0,width);end
assert(isnumeric(x) && ismatrix(x) && size(x,2)==width, ...
 'f77:exportInput','Unexpected %s shape',name);
end

function x=scalarfield(s,name,default)
x=fieldvalue(s,name,default);
assert((isnumeric(x) || islogical(x)) && isscalar(x), ...
 'f77:exportInput','Expected scalar field %s',name);
end

function x=fieldvalue(s,name,default)
if isstruct(s) && isscalar(s) && isfield(s,name) && ~isempty(s.(name))
 x=s.(name);
else
 x=default;
end
end

function writejson(path,value)
encoded=jsonencode(value,'PrettyPrint',true);
fid=fopen(path,'w','n','UTF-8');assert(fid>=0,'f77:exportIO','Cannot open %s',path);
guard=onCleanup(@()fclose(fid)); %#ok<NASGU>
fprintf(fid,'%s',encoded);
end
