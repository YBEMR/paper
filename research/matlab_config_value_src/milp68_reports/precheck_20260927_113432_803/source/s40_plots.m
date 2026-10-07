function s40_plots(folder)
summary=readtable(fullfile(folder,'main_summary.csv'),'TextType','string');
methods=readtable(fullfile(folder,'main_methods.csv'),'TextType','string');
mkdir(fullfile(folder,'figures')); packs=["L3_Q" "L3_S"];
rho=[1 1.5 2 3 4 6]; margins=[.05 .25 .5 .75 1];
cats=["A" "B" "C" "D" "N" "U"];
colors=[.55 .8 .6; .95 .8 .35; .95 .45 .3; .6 .2 .4; .75 .75 .75; .6 .65 .95];
for pack=packs
    f=figure('Visible','off','Position',[50 50 1450 460],'Color','w');
    layout=tiledlayout(1,3,'TileSpacing','compact');
    title(layout,pack+" | synthetic L3; grid 1 ms; horizon 60 ms",'Interpreter','none');
    for panel=1:3
        data=zeros(5,6); labels=strings(5,6);
        for a=1:5
            for b=1:6
                row=summary(summary.package==pack&summary.rho==rho(b)&summary.margin==margins(a),:);
                if panel==1, code=find(cats==row.class); label=row.class;
                else
                    p=methods(methods.trial==row.trial&methods.version=="P"+string(panel-2),:);
                    if all(p.reached_reference), code=1; label="OPT";
                    elseif any(p.valid), code=2; label="SAFE";
                    elseif any(p.thermal=="violation"), code=4; label="HEAT";
                    elseif any(p.status=="no_noheat_configuration"), code=5; label="N";
                    elseif any(p.status=="prefix_deadline_failure"), code=3; label="DEADLINE";
                    else, code=6; label="U/FAIL"; end
                end
                data(a,b)=code; labels(a,b)=label;
            end
        end
        ax=nexttile; imagesc(ax,data,[.5 6.5]); colormap(ax,colors); axis(ax,'tight');
        xticks(ax,1:6); xticklabels(ax,string(rho)); yticks(ax,1:5); yticklabels(ax,string(margins));
        xlabel(ax,'Deadline multiplier'); ylabel(ax,'Initial thermal headroom (larger = colder)');
        for a=1:5, for b=1:6, text(ax,b,a,labels(a,b),'HorizontalAlignment','center','FontSize',10); end; end
        if panel==1, title(ax,'Model class'); else, title(ax,"P"+string(panel-2)+" outcome"); end
    end
    exportgraphics(f,fullfile(folder,'figures',char(pack+"_matrix.png")),'Resolution',160); close(f);
end
end
