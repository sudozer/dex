import json
import pdb

pdb.set_trace()
fpath = "../telemetryDefinitions/o2o_tlm_db_new.pd"
a = json.load(open(fpath,'r'))
for pktName,pkt in a.items():
    for field in pkt['fields']:
        if field['fieldName'][0].isnumeric():
            field['fieldName']=f"d{field['fieldName']}"

json.dump(a,open(fpath,'w'),indent=4)
