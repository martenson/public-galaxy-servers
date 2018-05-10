import json
from influxdb import InfluxDBClient


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Send results to an InfluxDB server')
    parser.add_argument('--json', type=argparse.FileType('w'), help="Input .json file")
    parser.add_argument('--influx_db', default='test')
    parser.add_argument('--influx_ssl', action='store_true')
    parser.add_argument('--influx_host', default='influxdb')
    parser.add_argument('--influx_port', default=8086)
    parser.add_argument('--influx_user', default='root')
    parser.add_argument('--influx_pass', default='root')

    args = parser.parse_args()

    return_list = json.load(args.json)

    influx_kw = {
        'ssl': args.influx_ssl,
        'database': args.influx_db,
        'username': args.influx_user,
        'password': args.influx_pass
    }
    client = InfluxDBClient(args.influx_host, args.influx_port, **influx_kw)

    measurements = []
    for server in return_list:
        # Only send the data point if we have results to send.
        if 'results' not in server:
            continue

        if 'response_time' not in server['results']:
            continue

        measurement = {
            'measurement': 'server',
            'tags': {
                'location': server['location'],
                'name': server['name'],
                'galaxy': server['results']['galaxy'],
                'responding': server['results']['responding'],
                'version': server['results'].get('version', None),
            },
            'time': server['_reqtime'],
            'fields': {
                'value': 1,
                'code': server['results'].get('code', 0),
                'response_time': server['results']['response_time'],
                'gx_version': float(server['results'].get('version', 0)),
            }
        }

        if 'features' in server['results']:
            measurement['tags'].update({
                'allow_user_creation': server['results']['features'].get('allow_user_creation', False),
                'allow_user_dataset_purge': server['results']['features'].get('allow_user_dataset_purge', False),
                'enable_communication_server': server['results']['features'].get('enable_communication_server', False),
                'enable_openid': server['results']['features'].get('enable_openid', False),
                'enable_quotas': server['results']['features'].get('enable_quotas', False),
                'enable_unique_workflow_defaults': server['results']['features'].get('enable_unique_workflow_defaults', False),
                'has_user_tool_filters': server['results']['features'].get('has_user_tool_filters', False),
                'message_box_visible': server['results']['features'].get('message_box_visible', False),
                'require_login': server['results']['features'].get('require_login', False),
            })

        # If no galaxy is found AND no features are found (So we couldn't access the API)
        if not server['results']['galaxy'] and 'features' not in server['results']:
            measurement['fields']['value'] = 0
        measurements.append(measurement)

    client.write_points(measurements)
