function meta = htp_certificate_state(certificate)
%HTP_CERTIFICATE_STATE Preserve technical failure and partial-evidence states.
meta=struct('state',certificate.state,'rankable_energy',false,'technical_issue',false);
if isfield(certificate,'technical_issue'), meta.technical_issue=logical(certificate.technical_issue); end
if isfield(certificate,'reason')
    meta.technical_issue=meta.technical_issue || any(strcmp(certificate.reason, ...
        {'INTERNAL_CONSISTENCY_ERROR','NUMERICAL_ERROR','RESOURCE_LIMIT'}));
end
if strcmp(certificate.state,'SAFE')
    admissible=isfield(certificate,'complete') && certificate.complete && ...
        isfield(certificate,'rankable_energy') && certificate.rankable_energy && ...
        isfield(certificate,'energy_accuracy_met') && certificate.energy_accuracy_met && ...
        isfield(certificate,'energy_J') && ~isempty(certificate.energy_J) && ...
        (~isfield(certificate,'violations') || isempty(certificate.violations));
    if admissible && ~meta.technical_issue, meta.rankable_energy=true;
    else, meta.state='UNRESOLVED'; end
end
end
