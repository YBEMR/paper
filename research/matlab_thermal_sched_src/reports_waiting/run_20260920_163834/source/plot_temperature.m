function plot_temperature(pi1, pi2, cfg, th, fname, lbl1, lbl2)
% PLOT_TEMPERATURE  Compare 3-node temperature trajectories of two schedules.
%   PLOT_TEMPERATURE(pi1,pi2,cfg,th,fname)  saved to fname (PNG).
%   Optional lbl1/lbl2 set the legend labels.
if nargin < 6, lbl1 = 'schedule 1'; lbl2 = 'schedule 2'; end
sub = 4;
[t1, T1] = compute_trajectory(pi1, cfg, th, sub);
[t2, T2] = compute_trajectory(pi2, cfg, th, sub);
names = {'CPU core 1','CPU core 2','NPU'};
fig = figure('Visible','off','Position',[100 100 1000 780]);
for r = 1:3
  subplot(3,1,r);
  plot(t1, T1(:,r), 'b-', 'LineWidth', 1.6); hold on;
  plot(t2, T2(:,r), 'r--', 'LineWidth', 1.6);
  yline(cfg.T_lim, 'k-', 'T_{lim}');
  yline(cfg.T_amb, 'k:', 'T_{amb}');
  xlabel('time (ms)'); ylabel('temperature (C)');
  title(names{r}); grid on;
  ymin = min(cfg.T_amb, min([T1(:,r); T2(:,r)])) - 3;
  ymax = max(cfg.T_lim + 8, max([T1(:,r); T2(:,r)]) + 3);
  ylim([ymin, ymax]);
  if r == 1, legend({lbl1, lbl2},'Location','best'); end
end
exportgraphics(fig, fname, 'Resolution', 150);
close(fig);
end
