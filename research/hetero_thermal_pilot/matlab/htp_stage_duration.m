function d_s = htp_stage_duration(spec, f_Hz)
%HTP_STAGE_DURATION Evaluate a declared legal point; no extrapolation.
% kind: alpha, cycles_pwl, table. All numbers use seconds and Hz.
validateattributes(f_Hz, {'double'}, {'scalar','real','finite','positive'});
validateattributes(spec.freq_Hz, {'double'}, {'vector','real','finite','positive','nonempty'});
assert(numel(unique(spec.freq_Hz)) == numel(spec.freq_Hz), 'htp:DuplicateOPP', 'Duplicate legal frequencies.');
idx = find(spec.freq_Hz(:) == f_Hz);
assert(numel(idx) == 1, 'htp:IllegalOPP', 'Frequency is not in the declared legal set.');
switch char(spec.kind)
    case 'alpha'
        validateattributes(spec.dref_s, {'double'}, {'scalar','real','finite','positive'});
        validateattributes(spec.fref_Hz, {'double'}, {'scalar','real','finite','positive'});
        validateattributes(spec.sensitivity, {'double'}, {'scalar','real','finite','>=',0,'<=',1});
        assert(any(spec.freq_Hz == spec.fref_Hz), 'htp:ReferenceOPP', 'Reference frequency must be a declared point.');
        d_s = spec.dref_s * (1-spec.sensitivity + spec.sensitivity * spec.fref_Hz/f_Hz);
    case 'cycles_pwl'
        % C(f)=max_r(a_r*f+b_r), d(f)=C(f)/f. a in seconds, b in cycles.
        validateattributes(spec.a_s, {'double'}, {'vector','real','finite','nonempty'});
        validateattributes(spec.b_cycles, {'double'}, {'vector','real','finite','nonempty'});
        assert(numel(spec.a_s)==numel(spec.b_cycles), 'htp:CyclesShape', 'Incompatible envelope coefficients.');
        cycles = max(spec.a_s(:) * spec.freq_Hz(:)' + spec.b_cycles(:), [], 1);
        assert(all(cycles > 0), 'htp:CyclesPositive', 'Cycle envelope must be positive at every legal point.');
        d_s = cycles(idx) / f_Hz;
    case 'table'
        validateattributes(spec.duration_s, {'double'}, {'vector','real','finite','positive','nonempty'});
        assert(numel(spec.duration_s)==numel(spec.freq_Hz), 'htp:TableShape', 'One duration per legal point is required.');
        d_s = spec.duration_s(idx);
    otherwise
        error('htp:UnknownResponse', 'Unknown response kind.');
end
assert(isscalar(d_s) && isfinite(d_s) && d_s>0, 'htp:InvalidDuration', 'Invalid duration.');
end
