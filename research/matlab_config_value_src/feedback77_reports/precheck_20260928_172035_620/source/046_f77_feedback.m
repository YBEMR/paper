function out=f77_feedback(c,h,columns,q,rows,variant,check,inject)
% Construct one proposed feedback record; caller commits it within budget.
if nargin<7,check=@()[];end
if nargin<8,inject=struct();end
assert(strcmp(q.thermal.status,'violation'),'f77:feedback','Requires certified complete violation');
out=struct('kind','no_good','reason','no_good_policy','certificate',[], ...
 'duplicate',false,'existing_row_violation',~isempty(q.row_check.violated),'row',[]);
if strcmp(variant,'no_good'),return;end
assert(strcmp(variant,'thermal_row'));
check();thermal=q.thermal;
if isfield(inject,'point_at_zero') && inject.point_at_zero,thermal.peak_time(:)=0;end
certificate=t76_cut(c,h,columns,q.selected,thermal);check();out.certificate=certificate;
if strcmp(certificate.kind,'no_good'),out.reason='point_certificate_not_formed';return;end
assert(strcmp(certificate.kind,'temperature_row'),'f77:feedback','Unexpected cut state');
row=certificate.row;
for j=1:numel(rows)
 check();
 if isequal(row.coefficient_lower,rows{j}.coefficient_lower) && isequal(row.rhs_upper,rows{j}.rhs_upper)
  out.duplicate=true;break;
 end
end
if out.duplicate,out.reason='duplicate_temperature_row';
elseif out.existing_row_violation,out.reason='existing_temperature_row_violated';
else,out.kind='temperature_row';out.reason='certified_fixed_time';out.row=row;end
check();
end
