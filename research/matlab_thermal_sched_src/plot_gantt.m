function plot_gantt(pi, cfg, fname)
% PLOT_GANTT  Gantt chart of one schedule, saved to fname (PNG).
pi = pi(:)';
mA = pi(1); mB = pi(2); fA = pi(3); fB = pi(4);
sA1 = pi(5); sB1 = pi(6); sA2 = pi(7); sB2 = pi(8);
dA1 = cfg.d_A1_ms(fA); dB1 = cfg.d_B1_ms(fB);
dA2 = cfg.d_A2_ms; dB2 = cfg.d_B2_ms;
fl = {'L','H'};
H = cfg.H_ms;
% row mapping: y=3 -> C1, y=2 -> C2, y=1 -> NPU
rowA1 = 4 - mA; rowB1 = 4 - mB; rowN = 1;
fig = figure('Visible','off','Position',[100 100 950 300]);
hold on;
draw_bar(sA1, dA1, rowA1, [0.25 0.6 0.9], sprintf('A1(%s)', fl{fA}));
draw_bar(sB1, dB1, rowB1, [0.95 0.65 0.2], sprintf('B1(%s)', fl{fB}));
draw_bar(sA2, dA2, rowN, [0.4 0.8 0.4], 'A2');
draw_bar(sB2, dB2, rowN, [0.85 0.35 0.35], 'B2');
xline(cfg.D_A_ms, '--k', 'D_A');
xline(cfg.D_B_ms, '--m', 'D_B');
ylim([0.5 3.5]); xlim([0 H]);
yticks([1 2 3]); yticklabels({'NPU','C2','C1'});
xlabel('time (ms)'); grid on;
title(sprintf('Gantt  mA=%d mB=%d fA=%s fB=%s  E=%.3f mJ', ...
      mA, mB, fl{fA}, fl{fB}, energy_of(pi, cfg)*1e3));
exportgraphics(fig, fname, 'Resolution', 150);
close(fig);
end

function draw_bar(s,d,row,color,lbl)
x0 = s; w = d; y0 = row - 0.28;
rectangle('Position',[x0 y0 w 0.56],'FaceColor',color,'EdgeColor','k');
text(x0 + w/2, row, lbl, 'HorizontalAlignment','center','FontSize',9);
end

function E = energy_of(pi, cfg)
S = int32(pi(:)');
[Pc1, Pc2, Pn] = schedule_power(S, cfg);
E = sum(Pc1 + Pc2 + Pn, 2) * (cfg.delta_ms*cfg.s_per_ms);
end
