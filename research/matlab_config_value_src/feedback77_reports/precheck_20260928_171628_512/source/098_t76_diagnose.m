function r=t76_diagnose(design,id)
clock=tic;b=struct('timer',clock,'limit',60);check=@()s55_budget(b,'diagnostic76');
r=struct('id',id,'status','running','phase','input','complete',false,'elapsed_s',0, ...
 'rows',[],'thermal',{{}},'cuts',{{}},'checked_rows',0,'checked_cuts',0,'timing',struct);
try
 [trials,~]=s55_load(design);trial=trials(strcmp({trials.id},id));assert(isscalar(trial));c=trial.case;h=trial.thermal;check();
 r.trial=trial;r.phase='enumeration';mark=toc(clock);lib=s55_enumerate(c,b);check();
 assert(lib.complete,'t76:incomplete','Enumeration did not complete');lib=s55_sort(c,lib,b);check();
 assert(size(lib.rows,1)==288 && size(unique(lib.rows,'rows'),1)==288,'t76:count','Historical coverage count mismatch');
 r.rows=lib.rows;r.energy_J=lib.energy;r.timing.enumeration_sort_s=toc(clock)-mark;
 r.phase='option_encoding';mark=toc(clock);p=b68_build(c,check);selected=t76_option_ids(c,p.columns,lib.rows);
 [orbits,keys]=t76_orbits(c,lib.rows);check();r.columns=p.columns;r.selected=selected;r.orbits=orbits;r.orbit_keys=keys;
 r.timing.option_encoding_s=toc(clock)-mark;r.phase='continuous_classification';mark=toc(clock);
 for j=1:288
  check();s=s55_schedule(c,lib.rows(j,:));v=s55_validate(c,s);assert(v.feasible,v.reason);
  en=s55_energy(c,s);assert(abs(en.integral_J-en.sum_J)<=1e-12);
  thermal=b64_thermal(c,s,h);check();r.thermal{j}=thermal;r.checked_rows=j;
 end
 r.timing.continuous_classification_s=toc(clock)-mark;
 states=cellfun(@(x)x.status,r.thermal,'UniformOutput',false);bad=find(strcmp(states,'violation'));safe=find(strcmp(states,'safe'));
 r.phase='cut_coverage';mark=toc(clock);
 for k=1:numel(bad)
  check();j=bad(k);cut=t76_cut(c,h,p.columns,selected(j,:),r.thermal{j});check();
  cut.source_row=j;cut.no_good_excluded_row=j;cut.excluded_rows=[];cut.row_undecided=[];
  if strcmp(cut.kind,'temperature_row')
   tests=zeros(288,2);
   for z=1:288,check();tests(z,:)=t76_point(cut.row,selected(z,:));end
   cut.excluded_rows=find(tests(:,1)>cut.row.rhs_upper)';
   cut.row_undecided=find(tests(:,1)<=cut.row.rhs_upper & tests(:,2)>cut.row.rhs_upper)';cut.lhs_intervals=tests;
  elseif strcmp(cut.kind,'no_good'),cut.excluded_rows=j;
  else,error('t76:violation','A certified global violation must retain no-good fallback');end
  assert(ismember(j,cut.excluded_rows),'t76:source','Source must be excluded');
  assert(isempty(intersect(safe,cut.excluded_rows)),'t76:safe','A safe schedule was excluded');
  cut.excluded_orbits=unique(orbits(cut.excluded_rows))';cut.safe_removed=numel(intersect(safe,cut.excluded_rows));
  cut.violation_removed=numel(intersect(bad,cut.excluded_rows));
  cut.unknown_removed=numel(cut.excluded_rows)-cut.safe_removed-cut.violation_removed;
  check();r.cuts{k}=cut;r.checked_cuts=k;
 end
 r.timing.cut_coverage_s=toc(clock)-mark;check();r.complete=true;r.status='complete';r.phase='done';
catch err
 if strcmp(err.identifier,'s55:timeout'),r.status='timeout';
 else,r.status='error';r.error=getReport(err,'extended','hyperlinks','off');end
end
r.elapsed_s=toc(clock);
end
