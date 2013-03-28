'''
Arguments: [out_graph] [csv_file_1] [csv_file_2] ...

Outputs a single CDF graph based on the CSV files. Only the first column of each
CSV file will be processed, from which a CDF table will be automatically
computed.

Created on Mar 19, 2013

@author: danny
'''
from boomslang import Line, Plot
import sys
from lib.util import make_cdf_table

colors = ['black', 'red', 'blue',  'green', 'purple', 'cyan']
line_styles = ['--'] + ['-'] * (len(colors) - 1)


FONT_SIZE = 18

def main():

    output_graph = sys.argv[1]

    plot = Plot()
    plot.hasLegend(location='lower right')
    plot.xLabel = 'Per-client throughput (Mbps)'  # Change this
    plot.yLabel = 'CDF'
    plot.xLimits = (0, 50)
    plot.yLimits = (0, 1)
    plot.legendLabelSize = FONT_SIZE
    plot.xTickLabelSize = FONT_SIZE - 2
    plot.yTickLabelSize = FONT_SIZE - 2
    plot.axesLabelSize = FONT_SIZE
    
    for csv_file in sys.argv[2:]:
        
        cdf_table = _make_cdf(csv_file)
        
        line = Line()
        line.xValues = [x for (x, _) in cdf_table]
        line.yValues = [y for (_, y) in cdf_table]
        line.color = colors.pop(0)
        line.lineStyle = line_styles.pop(0)
        
        # Extract the filename
        line.label = capitalize( csv_file.split('/')[-2].replace('.csv', '') )
        plot.add(line)
        
    plot.save(output_graph)
    
    


def _make_cdf(csv_file, column=0, entry_count=None):
    
    inlist = []
    with open(csv_file) as csv_f:
        for line in csv_f:
            line = line.strip()
            if line:
                if ',' in line:
                    v = line.split(',')[column]
                elif '\t' in line:
                    v = line.split('\t')[column]
                else:
                    v = line.split()[column]
            inlist += [float(v)]
    
    if entry_count:
        inlist = inlist[0 : entry_count]
        inlist += [0] * (entry_count - len(inlist))
    
    return make_cdf_table(inlist)




def capitalize(s):
    return s.replace('hp', 'HP').replace('monaco', 'Monaco').replace('ovs', 'OVS').replace('quanta', 'Quanta')


if __name__ == '__main__':
    main()