function thv_plots(folder,trials,results)
mkdir(fullfile(folder,'figures'));
for k=[3 6 9]
    tr=trials(k); r=results{k};
    if isempty(r.optimal_mode_indices), continue; end
    first=r.reference.optimal_indices(1);
    orig=r.earliest([r.earliest.index]==first);
    witness=r.modes(r.optimal_mode_indices(1));
    [ta,Ta]=thv_trace(orig.evaluation,tr.thermal,.00001);
    [tb,Tb]=thv_trace(witness.evaluation,tr.thermal,.00001);
    f=figure('Visible','off','Color','w','Position',[100 100 1000 480]);
    plot(ta*1000,Ta(:,1),'r--',ta*1000,Ta(:,2),'b--', ...
        tb*1000,Tb(:,1),'r-',tb*1000,Tb(:,2),'b-','LineWidth',1.3);
    hold on; yline(80,'k:','Limit 80 C'); grid on;
    xlabel('Time (ms)'); ylabel('Temperature (C)');
    title({strrep(tr.id,'_','\_'),'One earliest representative versus a safe witness; not all earliest schedules'});
    legend('Earliest CPU','Earliest NPU','Witness CPU','Witness NPU','Location','best');
    exportgraphics(f,fullfile(folder,'figures',[tr.id '.png']),'Resolution',160); close(f);
    writetable(table(ta',Ta(:,1),Ta(:,2),'VariableNames',{'time_s','CPU_C','NPU_C'}), ...
        fullfile(folder,'figures',[tr.id '_earliest.csv']));
    writetable(table(tb',Tb(:,1),Tb(:,2),'VariableNames',{'time_s','CPU_C','NPU_C'}), ...
        fullfile(folder,'figures',[tr.id '_witness.csv']));
end
end
