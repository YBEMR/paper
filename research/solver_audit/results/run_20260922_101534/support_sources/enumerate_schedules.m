function S = enumerate_schedules(cfg, opts)
% ENUMERATE_SCHEDULES  Exhaustively enumerate all base-legal schedules.
%   S = ENUMERATE_SCHEDULES(cfg)            standard model
%   S = ENUMERATE_SCHEDULES(cfg, opts)      opts.remove_dependency = true
%                                           removes A1->A2 and B1->B2
%                                           (structural ablation A)
%
% Model: discrete start times on a 1-ms grid (cfg.delta_ms), non-preemptive,
% active waiting allowed. All stage durations are integer multiples of the grid.
%
% S is N x 8 (int32): [mA mB fA fB sA1 sB1 sA2 sB2]
%   mA,mB in {1,2}  : CPU core assignment of A1, B1
%   fA,fB in {1,2}  : 1 = low freq, 2 = high freq
%   sXXX            : start times (integer ms)
%
% Constraints enforced here (base set):
%   dependencies  : sA2 >= sA1+dA1, sB2 >= sB1+dB1   (unless ablated)
%   deadlines     : sA2+dA2 <= D_A, sB2+dB2 <= D_B
%   CPU exclusivity: if same core, A1/B1 intervals must not overlap
%   NPU exclusivity: A2/B2 intervals must not overlap
if nargin < 2, opts = struct(); end
if ~isfield(opts,'remove_dependency'), opts.remove_dependency = false; end
DA = cfg.D_A_ms; DB = cfg.D_B_ms;
dA2 = cfg.d_A2_ms; dB2 = cfg.d_B2_ms;
rA = 0; rB = 0;
if isfield(cfg,'rA_ms'), rA = cfg.rA_ms; end   % release time of request A (A1)
if isfield(cfg,'rB_ms'), rB = cfg.rB_ms; end   % release time of request B (B1)
S = zeros(0,8,'int32');
for mA = 1:2
  for mB = 1:2
    for fA = 1:2
      for fB = 1:2
        dA1 = cfg.d_A1_ms(fA); dB1 = cfg.d_B1_ms(fB);
        if opts.remove_dependency
            sA1max = DA - dA1;                 % B2/A2 may run before its CPU stage
            sB1max = DB - dB1;
        else
            sA1max = DA - dA1 - dA2;
            sB1max = DB - dB1 - dB2;
        end
        if sA1max < rA || sB1max < rB, continue; end
        sA2max = DA - dA2; sB2max = DB - dB2;
        [gA1,gB1,gA2,gB2] = ndgrid(rA:sA1max, rB:sB1max, 0:sA2max, 0:sB2max);
        gA1=gA1(:); gB1=gB1(:); gA2=gA2(:); gB2=gB2(:);
        ok = true(numel(gA1),1);
        if ~opts.remove_dependency
          ok = ok & (gA2 >= gA1 + dA1);
          ok = ok & (gB2 >= gB1 + dB1);
        end
        ok = ok & (gA2 + dA2 <= DA);
        ok = ok & (gB2 + dB2 <= DB);
        if mA == mB
          ok = ok & ((gA1 + dA1 <= gB1) | (gB1 + dB1 <= gA1));
        end
        ok = ok & ((gA2 + dA2 <= gB2) | (gB2 + dB2 <= gA2));
        n = sum(ok);
        if n > 0
          blk = int32([mA*ones(n,1), mB*ones(n,1), fA*ones(n,1), fB*ones(n,1), ...
                       gA1(ok), gB1(ok), gA2(ok), gB2(ok)]);
          S = [S; blk];
        end
      end
    end
  end
end
end
