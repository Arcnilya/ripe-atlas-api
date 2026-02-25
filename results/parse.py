#!/usr/bin/env python3

import json
import base64
import argparse
import dns.message
import dns.edns
import pandas as pd

def read_json(fname):
    with open(fname, "r") as fp:
        content = fp.read().strip()

        # Try to parse as a full JSON structure first
        try:
            data = json.loads(content)
            if isinstance(data, list):
                return data
            else:
                return [data]  # single JSON object
        except json.JSONDecodeError:
            # Fall back to line-by-line parsing
            return [json.loads(line) for line in content.splitlines() if line.strip()]

        return json.load(fp)


def print_EDE(dnsmsg):
    if dnsmsg.options:
        for option in dnsmsg.options:
            if option.otype == dns.edns.EDE:
                print(f"EDE Code: {option.code}, Text: {option.text}")


def parse_buf(buf):
    return dns.message.from_wire(base64.b64decode(buf))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--header", action="store_true", help="prints header (column names)")
    parser.add_argument("--semi", action="store_true", help="use semicolon as separator")
    parser.add_argument("-i", "--input", required=True, help="json file to read")
    parser.add_argument("-o", "--output", help="csv file to write")
    args = parser.parse_args()

    measurement = read_json(args.input)
    header = ["time","probeID","probeIP","resolverIP","query","rcode","answer","nscount"]
    #df = pd.DataFrame(columns=header)
    rows = []
    for probe in measurement:
        for query in probe["resultset"]:
            entry = {}
            entry["time"] = query["time"]
            entry["probeID"] = probe["prb_id"]
            entry["probeIP"] = probe["from"]
            if "dst_addr" in query:
                entry["resolverIP"] = query["dst_addr"]
            if "result" in query:
                try:
                    dnsmsg = parse_buf(query["result"]["abuf"])
                    #print_EDE(dnsmsg)
                    answer = str(dnsmsg).splitlines()
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
                except:
                    entry["nscount"] = query["result"]["NSCOUNT"]
            rows.append(entry)
            #df = df.append(entry, ignore_index=True)
    df = pd.DataFrame(rows, columns=header)

    if args.output:
        separator = ";" if args.semi else ","
        df.to_csv(args.output, index=False, header=args.header, sep=separator)
    else:
        print(df.to_string())


if __name__ == "__main__":
    main()
