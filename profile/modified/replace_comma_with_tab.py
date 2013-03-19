import sys

for filename in sys.argv[1:]:
    
    with open(filename) as f:
        data = f.read()

    data = data.replace(',', '\t')

    with open(filename, 'w') as f:
        f.write(data)


