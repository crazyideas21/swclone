import sys

for filename in sys.argv[1:]:

    values = []
    with open(filename) as f:
        for line in f:
            line = line.strip()
            if line:
                v = line.split()[0]
                values += [float(v)]

    values.sort()
    
    with open(filename, 'w') as f:
        for index in range(len(values)):
            print >> f, '%f\t%f' % (values[index], (index+1.0)/len(values))
