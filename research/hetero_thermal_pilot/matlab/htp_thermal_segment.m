function out = htp_thermal_segment(C_JK, G_WK, b_W, lambda_WK, theta0_K, dt_s)
%HTP_THERMAL_SEGMENT Coupled RC propagation at fixed OPP/activity state.
% theta=T-Tambient. Local power is b+lambda.*theta, including baseline once.
% Electrical sources and thermal nodes must already have matching boundaries.
% This function does NOT certify continuous peak temperature or schedule safety.
validateattributes(C_JK, {'double'}, {'column','real','finite','positive','nonempty'});
n = numel(C_JK);
validateattributes(G_WK, {'double'}, {'size',[n n],'real','finite'});
validateattributes(b_W, {'double'}, {'size',[n 1],'real','finite','nonnegative'});
validateattributes(lambda_WK, {'double'}, {'size',[n 1],'real','finite','nonnegative'});
validateattributes(theta0_K, {'double'}, {'size',[n 1],'real','finite','nonnegative'});
validateattributes(dt_s, {'double'}, {'scalar','real','finite','nonnegative'});
assert(isequal(G_WK,G_WK'), 'htp:ConductanceSymmetry', 'Conductance must be exactly symmetric.');
off = G_WK-diag(diag(G_WK));
assert(all(off(:)<=0) && all(sum(G_WK,2)>=0), 'htp:PassiveConductance', 'Invalid passive conductance network.');
[~,flag] = chol(G_WK);
assert(flag==0, 'htp:NoHeatSink', 'Conductance must be positive definite with an ambient heat path.');
A = diag(1./C_JK) * (-G_WK+diag(lambda_WK));
g = b_W./C_JK;
% Augment temperature, accumulated electrical energy, and the constant state.
M = zeros(n+2);
M(1:n,1:n) = A;
M(1:n,n+2) = g;
M(n+1,1:n) = lambda_WK';
M(n+1,n+2) = sum(b_W);
z0 = [theta0_K;0;1];
last = state_at(M,z0,b_W,lambda_WK,n,dt_s,dt_s);
out.end_theta_K = last.theta_K;
out.energy_J = last.energy_J;
out.sample = @(t_s) state_at(M,z0,b_W,lambda_WK,n,dt_s,t_s);
out.max_real_eigenvalue_per_s = max(real(eig(A)));
out.stable_numerical_indicator = out.max_real_eigenvalue_per_s < 0;
out.safety_status = 'UNASSESSED';
out.numeric_scope = 'double precision expm; no outward error enclosure';
end

function value = state_at(M,z0,b,lambda,n,dt,t)
validateattributes(t, {'double'}, {'scalar','real','finite','nonnegative','<=',dt});
z = expm(M*t)*z0;
assert(all(isfinite(z)), 'htp:NonfinitePropagation', 'Propagation is nonfinite.');
value.time_s = t;
value.theta_K = z(1:n);
value.energy_J = z(n+1);
value.power_W = b+lambda.*value.theta_K;
end
