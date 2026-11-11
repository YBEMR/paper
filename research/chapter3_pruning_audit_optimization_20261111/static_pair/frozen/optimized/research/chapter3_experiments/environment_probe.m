function environment_probe(output)
% Environment check only: no optimization problem or research case is solved.
info = struct('version', version, 'release', version('-release'), ...
    'intlinprog_path', which('intlinprog'), ...
    'license_test', license('test', 'Optimization_Toolbox'));
[ok, message] = license('checkout', 'Optimization_Toolbox');
info.license_checkout = logical(ok);
info.license_message = message;
info.solver_executed = false;
fid = fopen(output, 'w', 'n', 'UTF-8');
if fid < 0, error('chapter3:probeOutput', 'Cannot open probe output'); end
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', jsonencode(info));
end
