function [d,Q] = cv_response(c,model)
% Rows: requests A,B. Columns: low,high.
x=[c.q 1]; a=c.alpha(:);
if strcmp(model,'simple'), a=ones(2,1); end
assert(ismember(model,{'simple','task'}),'Unknown response model');
d=c.dref(:).*((1-a)+a./x);
Q=c.u(:)+c.v(:).*x.^2;
end
