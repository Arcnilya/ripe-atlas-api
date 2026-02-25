# RIPE Atlas API
This is a python script for running measurements using RIPE Atlas probes
from your terminal.

Request 50 probes from Sweden to query www.example.com:
```bash
python3 main.py create -d "Description" -q www.example.com -p 50 -c SE
```

Request 100 probes in the world to query CH version.bind TXT:
```bash
python3 main.py create -d "Description" -q version.bind --qclass CHAOS -r TXT -p 100 -a WW
```

Multiple queries:
```bash
python3 main.py create -d "Description" -q queries.txt
```

List status of measurements
```bash
python3 main.py status
```

Download measurement results
```bash
python3 main.py fetch -m {measurementID}
```

## Todo
- [x] python3 main.py fetch -o outdir
- [x] Include description in the outfile name
- [ ] python3 main.py parse (instead of parse.py)
- [ ] python3 main.py fetch "search string"
