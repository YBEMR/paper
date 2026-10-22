"""Layout-only redraw of saved final-analysis figures; no new evidence."""
import json
from pathlib import Path
import analyse_combined_deadline as c


def main():
    out=c.RESUME/'analysis01'
    facts_path=out/'facts.json'
    facts=json.loads(facts_path.read_text(encoding='utf-8'))
    if facts.get('prefix_only') or not (c.RESUME/'process_terminal.json').is_file():
        raise ValueError('Only an existing terminal analysis may be redrawn')
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib.figure import Figure
    original=Figure.savefig
    def savefig(figure, path, **kwargs):
        # A retained-but-unaccepted U adds a tenth legend entry and a second
        # legend row. Leave space below the axis labels in the stopped plot.
        if Path(path).name=='best_safe_upper_bound_and_L0.png':
            for legend in figure.legends:
                legend.set_bbox_to_anchor((.5,-.14), transform=figure.transFigure)
        return original(figure,path,**kwargs)
    Figure.savefig=savefig
    try:
        c.figures(out,facts)
    finally:
        Figure.savefig=original
    record={'protocol':'K164-terminal-layout-only-plot-review-v1',
        'source_facts_sha256':c.a.sha(facts_path),
        'analysis_script_sha256':c.a.sha(c.HERE/'analyse_combined_deadline.py'),
        'render_script_sha256':c.a.sha(Path(__file__)),
        'adjustment':'Move two-row U/L0 legend below x-axis labels; saved values and marks unchanged',
        'plot_sha256':{name:c.a.sha(out/name) for name in (
            'best_safe_upper_bound_and_L0.png','P0_deadline_two_level_energy.png')},
        'scientific_data_changed':False,'new_solver_thermal_or_post_calls':0}
    with (out/'plot_render02.json').open('x',encoding='utf-8') as stream:
        json.dump(record,stream,ensure_ascii=False,indent=2);stream.write('\n')


if __name__=='__main__':
    main()
