#!/usr/bin/env python
import argparse
import re
import requests


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Notify the PGS dashboard that a Galaxy release has occurred')
    parser.add_argument('pr')
    parser.add_argument('--version', help="Specify if this cannot be auto-detected.")
    parser.add_argument('--influx_host')
    parser.add_argument('--influx_port')
    parser.add_argument('--influx_db')
    args = parser.parse_args()

    data = requests.get('https://api.github.com/repos/galaxyproject/galaxy/pulls/' + args.pr).json()
    if data['state'] != 'closed':
        raise Exception("Pull request not merged yet")

    if not data['merged_at']:
        raise Exception("Pull request not merged yet")

    version = None
    if 'release notes' in data['title']:
        versions = re.findall('^\[([0-9.]{4,})\]', data['title'])
        if len(versions) == 1:
            version = versions[0]

    if not version:
        if args.version:
            version = args.version
        else:
            raise Exception("Could not detect version, please specify with --version")

    from influxdb import InfluxDBClient
    client = InfluxDBClient(args.influx_host, args.influx_port, database=args.influx_db)
    measurement = {
        'measurement': 'events',
        'tags': {
            'tags': 'release',
            'description': 'Galaxy version %s was officially released on GitHub.<br/><br/><a href="https://docs.galaxyproject.org/en/master/releases/%s_announce.html">Release notes</a>' % (version, version)
        },
        'time': data['merged_at'],
        'fields': {
            'value': "Galaxy %s Released" % version,
        }
    }
    print(measurement)
    client.write_points([measurement])
