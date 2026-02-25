#!/usr/bin/env python3

import os
import json
import base64
import requests
import argparse
import dns.message

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


def status(args):
    if not os.path.exists(DB):
        exit(f"{DB} not found")
    with open(DB) as fp:
        for measurementID in json.load(fp).keys():
            session = requests.Session()
            measurement = session.get(
                f"{URL}/{measurementID}", headers={"Content-Type": "application/json"}
            ).json()
            print(measurementID, f"\"{measurement['description']}\"", f"({measurement['status']['name']})")


def parse_buf(buf):
    print(dns.message.from_wire(base64.b64decode(buf)))


def fetch(args):
    session = requests.Session()
    measurement_result = session.get(
        f"{URL}/{args.measurement}/results/?format=json", 
        headers={"Content-Type": "application/json"}
    ).json()

    if args.verbose:
        for probe in measurement_result:
            print(probe["prb_id"])
            for resolver in probe["resultset"]:
                if "result" in resolver.keys():
                    parse_buf(resolver["result"]["abuf"])
                else:
                    print("No result")
                print("="*40)
    
    measurement_details = session.get(
        f"{URL}/{args.measurement}", headers={"Content-Type": "application/json"}
    ).json()

    description = (measurement_details['description']).replace(" ", "_")
    sanitized_description = "".join(c for c in description if c.isalnum() or c in ('.', '_')).rstrip()
    fname = f"{args.out}/{sanitized_description}-{args.measurement}.json"
    os.makedirs(os.path.dirname(fname), exist_ok=True)
    with open(fname, "w") as fp:
        json.dump(measurement, fp)
    print("Saved to", fname)


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

    parser_status = subparsers.add_parser('status', help='Status of measurements') 

    parser_fetch = subparsers.add_parser('fetch', 
        help='Download result of measurement') 
    parser_fetch.add_argument("-m", "--measurement", required=True,
        help="Measurement ID to download results")
    parser_fetch.add_argument("-o", "--out", default="results",
        help="Set measurement output directory")

    args = parser.parse_args()

    if args.action == "create":
        create(args)
    if args.action == "status":
        status(args)
    if args.action == "fetch":
        fetch(args)

if __name__ == "__main__":
    main()

