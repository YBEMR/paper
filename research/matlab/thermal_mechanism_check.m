function thermal_mechanism_check
% Synthetic mechanism check, NOT measured CPU/NPU parameters or validation.
% One lumped thermal node represents an abstract executing resource.
% Same job: fast mode 7 W x 2 s; slow mode 5 W x 3 s. Deadline = 3 s.
% Ambient 25 degC, resistance 10 K/W, time constant 10 s, limit 80 degC.
% No claim is made that these values describe a particular CPU or NPU.
outdir = fileparts(mfilename('fullpath'));
ambient = 25; resistance = 10; tau = 10; limit = 80;
power = [7; 5]; duration = [2; 3]; initial = [40; 78];
mode = ["fast"; "slow"]; rows = cell(4, 8); idx = 0;
for s = 1:2
    for m = 1:2
        idx = idx + 1;
        equilibrium = ambient + resistance * power(m);
        endpoint = equilibrium + (initial(s)-equilibrium)*exp(-duration(m)/tau);
        % A single constant-power scalar RC segment is monotonic.
        % For coupled multi-node models, endpoints alone may miss interior peaks.
        peak = max(initial(s), endpoint);
        rows(idx,:) = {initial(s), mode(m), power(m), duration(m), ...
            power(m)*duration(m), endpoint, peak <= limit, equilibrium <= limit};
    end
end
result = cell2table(rows, 'VariableNames', {'Initial_C','Mode','Power_W', ...
    'Duration_s','Energy_J','End_C','TransientFeasible','SteadyFeasible'});
disp(result);
assert(result.TransientFeasible(1) && ~result.SteadyFeasible(1));
assert(~result.TransientFeasible(3) && result.TransientFeasible(4));
assert(result.Energy_J(1) < result.Energy_J(2));
% Cross-check exact solution with an independently integrated ODE.
[~, ode_temp] = ode45(@(~,T)(ambient+resistance*power(1)-T)/tau, ...
    [0 duration(1)], initial(2), odeset('RelTol',1e-10,'AbsTol',1e-10));
assert(abs(ode_temp(end)-result.End_C(3)) < 1e-6);
writetable(result, fullfile(outdir, 'thermal_mechanism_results.csv'));
fprintf('PASS: thermal history changes the feasible energy-minimizing mode.\n');
fprintf('PASS: steady-state constraint rejects a safe cold-start pulse.\n');
fprintf('Scope: illustrative scalar RC only; no hardware or full scheduler validation.\n');
end
