'''
Plot graphs for HotSDN.

Arguments: [graph_type] [output_graph] [csv_dir_1] [csv_dir_2] ...

where [graph_type] is either 'latency' or 'throughput'.

Created on Mar 17, 2013

@author: danny
'''
from boomslang import PlotLayout, Plot, Line  #@UnresolvedImport
import sys, os


colors = ['black', 'red', 'blue',  'green', 'purple', 'cyan']
line_styles = ['--'] + ['-'] * (len(colors) - 1)

def latency(output_graph_filename, csv_file_dir_list):
    """
    Plots three graphs side-by-side. First, redis performance; second, pkt-in
    latency; third, pkt-out latency.
    
    """
    layout = PlotLayout()
    redis_plot = Plot()
    pkt_in_plot = Plot()
    flow_mod_plot = Plot()
    
    for plot in (redis_plot, pkt_in_plot, flow_mod_plot):
        plot.hasLegend(location='lower right')
        plot.yLabel = 'CDF'
    
    redis_plot.xLabel = '(a) Query completion time (ms)'
    pkt_in_plot.xLabel = '(b) Switch processing time for ingress (ms)'
    flow_mod_plot.xLabel = '(c) Switch processing time for egress (ms)'
    
    for csv_dir in csv_file_dir_list:
        
        color = colors.pop(0)
        line_style = line_styles.pop(0)
        attr_dict = {'color': color, 'label': csv_dir.split('/')[-2], 
                     'yLimits': (0, 1), 'lineStyle': line_style}
        
        redis_line = get_line_from_csv(os.path.join(csv_dir, 'async_redis_latency.csv'), 
                                       xLimits=(0,400), **attr_dict) 
        pkt_in_line = get_line_from_csv(os.path.join(csv_dir, 'pkt_in_durations.csv'), 
                                        xLimits=(0,140), **attr_dict) 
        flow_mod_line = get_line_from_csv(os.path.join(csv_dir, 'flow_mod_durations.csv'), 
                                          xLimits=(0,140), **attr_dict) 
        
        redis_plot.add(redis_line)
        pkt_in_plot.add(pkt_in_line)
        flow_mod_plot.add(flow_mod_line)
    
    layout.addPlot(redis_plot)
    layout.addPlot(pkt_in_plot)
    layout.addPlot(flow_mod_plot)
    layout.width = 3
    
    layout.save('data/graphs/' + output_graph_filename + '.pdf')
    print 'Done.'



def get_line_from_csv(filename, **attr_dict):

    xs = []
    ys = []
    
    with open(filename) as fobj:
        for line in fobj:
            line = line.strip()
            if line:
                if ',' in line:
                    (x, y) = line.split(',')
                elif '\t' in line:
                    (x, y) = line.split('\t')
                else:
                    (x, y) = line.split()
                xs += [float(x)]
                ys += [float(y)]
                
    line = Line()
    line.xValues = xs
    line.yValues = ys
    
    for (attr, value) in attr_dict.items():
        setattr(line, attr, value)
    
    return line             

def main():
    
    if sys.argv[1] == 'latency':
        latency(sys.argv[2], sys.argv[3:])
    
    


if __name__ == '__main__':
    main()