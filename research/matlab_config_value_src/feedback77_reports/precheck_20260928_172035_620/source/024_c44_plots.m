function c44_plots(folder,trials,runs)
% Preselected representative cold/hot and deadline contrast, not benefit-picked.
for k=[1 2 4]
    tr=trials(k); fig=figure('Visible','off','Position',[50 50 1150 680]);
    tiledlayout(2,2); colors=lines(4);
    for j=1:2
        r=runs{k,j}; s=r.schedule;
        nexttile(j); hold on;
        for i=1:4
            if ~isfinite(s.start(i)), continue; end
            rectangle('Position',[1000*s.start(i),s.unit(i)-.3,1000*s.duration(i),.6],'FaceColor',colors(i,:));
            text(1000*(s.start(i)+s.duration(i)/2),s.unit(i),sprintf('%d',i),'HorizontalAlignment','center');
        end
        yticks(1:3); yticklabels({'CPU1','CPU2','NPU'}); ylim([.4 3.6]); xlim([0 max(tr.case.deadline)*1000]);
        xlabel('Time (ms)'); title([tr.id ' ' r.version ' ' r.status],'Interpreter','none'); grid on;
        nexttile(j+2);
        z=c44_thermal(tr.case,s,tr.thermal); [tt,T]=thv_trace(z,tr.thermal,.0001);
        plot(tt*1000,T,'LineWidth',1.2); hold on; yline(80,'--');
        xlabel('Time (ms)'); ylabel('Temperature (C)'); legend('CPU','NPU','Limit','Location','best'); grid on;
        title(sprintf('Continuous peaks %.5f / %.5f C',z.peak));
    end
    exportgraphics(fig,fullfile(folder,[tr.id '_schedule_temperature.png']),'Resolution',130); close(fig);
end
end
