#!/usr/bin/env python3

import json
import base64
import argparse
import dns.message
import pandas as pd

def read_json(fname):
    with open(fname, "r") as fp:
        return json.load(fp)


def parse_buf(buf):
    return dns.message.from_wire(base64.b64decode(buf))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--header", action="store_true", help="prints header (column names)")
    parser.add_argument("-i", "--input", required=True, help="json file to read")
    parser.add_argument("-o", "--output", help="csv file to write")
    args = parser.parse_args()

    measurement = read_json(args.input)
    header = ["time","probeID","probeIP","resolverIP","query","rcode","answer","nscount"]
    df = pd.DataFrame(columns=header)
    for probe in measurement:
        for query in probe["resultset"]:
            entry = {}
            entry["time"] = query["time"]
            entry["probeID"] = probe["prb_id"]
            entry["probeIP"] = probe["from"]
            if "dst_addr" in query:
                entry["resolverIP"] = query["dst_addr"]
            if "result" in query:
                answer = str(parse_buf(query["result"]["abuf"])).splitlines()
                for i in range(len(answer)):
                    if answer[i] == ";QUESTION":
                        if not answer[i+1].startswith(";"): # ;ANSWER
                            entry["query"] = answer[i+1]
                    if answer[i].startswith("rcode"):
                        entry["rcode"] = answer[i].split()[-1]
                    if answer[i] == ";ANSWER":
                        if not answer[i+1].startswith(";"): # ;AUTHORITY
                            entry["answer"] = answer[i+1]
                entry["nscount"] = query["result"]["NSCOUNT"]
            df = df.append(entry, ignore_index=True)

    if args.output:
        df.to_csv(args.output, index=False, header=args.header)
    else:
        print(df.to_string())


if __name__ == "__main__":
    main()
