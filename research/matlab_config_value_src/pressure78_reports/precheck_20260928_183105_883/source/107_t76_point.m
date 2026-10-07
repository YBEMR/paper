function value=t76_point(row,selected)
% Lower coefficients define the cut; interval summation certifies its test.
v=row.coefficient_lower(selected);value=t76_iv('sum',[v v]);
end
