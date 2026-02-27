#!/usr/bin/env python3

import os
import json
import base64
import requests
import argparse
import dns.message
import dns.edns
import pandas as pd

def read_file(fname):
    with open(fname, "r") as fp:
        return fp.read().splitlines()

apikey = read_file("apikey")[0]
URL = "https://atlas.ripe.net/api/v2/measurements"
DB = "measurements.json"


def probe_type(args):
    if args.country:
        return "country"
    if args.msm:
        return "msm" # same amount!
    return "area"
    
def probe_value(args):
    if args.area:
        return args.area
    if args.country:
        return args.country
    if args.msm:
        return args.msm # same amount!
    return "WW"


def payload(args, query):
    return  {
                "description": f"{args.description}",
                "type": "dns",
                "af": 4, # IPv4/6
                "is_oneoff": True,
                "query_class": args.qclass or "IN",
                "query_type": args.rr,
                "query_argument": query,
                "include_qbuf": True,
                "use_macros": True,
                "use_probe_resolver": True # need "target" if False
            }




# ==== Main functions (create, status, fetch, parse) ===

def create(args):
    if os.path.exists(args.query):
        queries = read_file(args.query)
    else:
        queries = (args.query).split(',')

    session = requests.Session()
    session.headers.update({
        "Authorization": f"Key {apikey}"
    })
    data = {
        "definitions": [payload(args, q) for q in queries],
        "probes": [{
            "requested": args.probes,
            "type": probe_type(args),
            "value": probe_value(args)
        }]
    }
    response = session.post(
        f"{URL}",
        json=data,
        headers={"Content-Type": "application/json"}
    ).json()

    if "measurements" not in response:
        exit(f"ERROR: {response}")

    if not os.path.exists(DB):
        measurements = {}
    else:
        with open(DB) as fp:
            measurements = json.load(fp)

    for measurementID in response["measurements"]:
        print("Measurement", str(measurementID), "created") 
        measurements.update({measurementID: data})

    with open(DB, "w") as fp:
        json.dump(measurements, fp)


def status_aux(measurementID):
    session = requests.Session()
    measurement = session.get(
        f"{URL}/{measurementID}", headers={"Content-Type": "application/json"}
    ).json()
    print(measurementID, f"\"{measurement['description']}\"", f"({measurement['status']['name']})")


def status(args):
    if not os.path.exists(DB):
        exit(f"{DB} not found")
    with open(DB) as fp:
        local_data = json.load(fp)
        for measurementID in local_data.keys():
            if args.search:
                for definition in local_data[measurementID]["definitions"]:
                    if args.search in definition["description"]:
                        status_aux(measurementID)
            else:
                status_aux(measurementID)


def fetch_aux(measurement_id, output_directory, verbose):
    session = requests.Session()
    measurement_result = session.get(
        f"{URL}/{measurement_id}/results/?format=json", 
        headers={"Content-Type": "application/json"}
    ).json()

    if verbose:
        for probe in measurement_result:
            print(probe["prb_id"])
            for resolver in probe["resultset"]:
                if "result" in resolver.keys():
                    print(dns.message.from_wire(base64.b64decode(resolver["result"]["abuf"])))
                else:
                    print("No result")
                print("="*40)
    
    measurement_details = session.get(
        f"{URL}/{measurement_id}", headers={"Content-Type": "application/json"}
    ).json()

    description = (measurement_details['description']).replace(" ", "_")
    sanitized_description = "".join(c for c in description if c.isalnum() or c in ('.', '_')).rstrip()
    fname = f"{output_directory}/{sanitized_description}-{measurement_id}.json"
    os.makedirs(os.path.dirname(fname), exist_ok=True)
    with open(fname, "w") as fp:
        json.dump(measurement_result, fp)
    print("Saved to", fname)


def fetch(args):
    if args.measurement: # single fetch
        fetch_aux(args.measurement, args.out, args.verbose)
    elif args.search: # search through descriptions
        measurements = set()
        with open(DB) as fp: # use local DB
            local_data = json.load(fp)
            for measurementID in local_data.keys():
                for definition in local_data[measurementID]["definitions"]:
                    if args.search in definition["description"]:
                        measurements.add(measurementID)
        for measurement in measurements:
            fetch_aux(measurement, args.out, args.verbose)
    else:
        print("Use -m or -s to fetch measurement(s)")


# ==== Help functions for parse() ====

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


def parse_aux(fname, args):
    measurement = read_json(fname)
    header = ["time","probeID","probeIP","resolverIP","query","rcode","answer","nscount","fname"]
    rows = []
    for probe in measurement:
        for query in probe["resultset"]:
            entry = {}
            entry["fname"] = os.path.basename(fname)
            entry["time"] = query["time"]
            entry["probeID"] = probe["prb_id"]
            entry["probeIP"] = probe["from"]
            if "dst_addr" in query:
                entry["resolverIP"] = query["dst_addr"]
            if "result" in query:
                try:
                    dnsmsg = dns.message.from_wire(base64.b64decode(query["result"]["abuf"]))
                    #print_EDE(dnsmsg)
                    entry["nscount"] = query["result"]["NSCOUNT"]
                    answer = str(dnsmsg).splitlines()
                    for i in range(len(answer)):
                        if answer[i] == ";QUESTION":
                            if not answer[i+1].startswith(";"): # ;ANSWER
                                entry["query"] = answer[i+1]
                        if answer[i].startswith("rcode"):
                            entry["rcode"] = answer[i].split()[-1]
                        if answer[i] == ";ANSWER":
                            j = 1
                            while not answer[i+j].startswith(";"): # ;AUTHORITY
                                tmp = entry.copy()
                                tmp["answer"] = answer[i+j]
                                rows.append(tmp)
                                j += 1
                            if j == 1: # found no answers
                                rows.append(entry)
                except:
                    rows.append(entry)
    df = pd.DataFrame(rows, columns=header)
    return df


def parse(args):
    out_dfs = []
    if os.path.isfile(args.input):
        out_dfs.append(parse_aux(args.input, args))
    if os.path.isdir(args.input):
        for f in os.listdir(os.fsencode(args.input)):
            fname = os.fsdecode(f)
            if fname.endswith(".json"):
                out_dfs.append(parse_aux(os.path.join(args.input, fname), args))

    df = pd.concat(out_dfs)
    if args.output:
        separator = ";" if args.semi else ","
        df.to_csv(args.output, index=False, header=args.header, sep=separator)
    else:
        print(df.to_string())



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    subparsers = parser.add_subparsers(dest='action', required=True, help='Subcommands')

    parser_create = subparsers.add_parser('create', 
        help='Create a measurement') 
    parser_create.add_argument("-d", "--description", required=True,
        help="Measurement description")
    parser_create.add_argument("--qclass",
        help="DNS query class (IN, CHAOS)")
    parser_create.add_argument("-q", "--query", required=True,
        help="DNS query")
    parser_create.add_argument("-r", "--rr", default="A",
        help="DNS resource record")
    parser_create.add_argument("-p", "--probes", type=int, default=5,
        help="Number of probes")
    parser_create.add_argument("-c", "--country", 
        help="Probe(s) country code")
    parser_create.add_argument("-a", "--area",
        help="Probe(s) area: WW (Worldwide), West, North-Central, South-Central, North-East, South-East")
    parser_create.add_argument("-m", "--msm", 
        help="Probe(s) from measurement ID")

    parser_status = subparsers.add_parser('status', 
        help='Status of measurements') 
    parser_status.add_argument("-s", "--search",
        help="Local search in descriptions for measurement(s)")

    parser_fetch = subparsers.add_parser('fetch', 
        help='Download result of measurement') 
    parser_fetch.add_argument("-m", "--measurement",
        help="Measurement ID to download results")
    parser_fetch.add_argument("-s", "--search",
        help="Local search in descriptions for measurement(s)")
    parser_fetch.add_argument("-o", "--out", default="results",
        help="Set measurement output directory")

    parser_parse = subparsers.add_parser('parse',
        help='Parse a measurement')
    parser_parse.add_argument("--header", action="store_true", 
        help="prints header (column names)")
    parser_parse.add_argument("--semi", action="store_true", 
        help="use semicolon as separator")
    parser_parse.add_argument("-i", "--input", required=True, 
        help="json file to read")
    parser_parse.add_argument("-o", "--output", 
        help="csv file to write")

    args = parser.parse_args()

    if args.action == "create":
        create(args)
    if args.action == "status":
        status(args)
    if args.action == "fetch":
        fetch(args)
    if args.action == "parse":
        parse(args)

if __name__ == "__main__":
    main()

