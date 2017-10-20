#!/usr/bin/env python
import argparse
import csv
import datetime
import json
import logging
import multiprocessing.pool
import os
import requests
import simplejson
logging.basicConfig(level=logging.DEBUG)
CONCURRENCY = 20
influxdb_enabled = True
USER_AGENT = 'Galaxy Public Server Monitoring Bot (+https://github.com/martenson/public-galaxy-servers)'
HEADERS = {'User-Agent': USER_AGENT}


def munge(value):
    if value == 'yes':
        return True
    elif value == 'no':
        return False
    elif len(value.strip()) == 0:
        return None
    else:
        return value


INTERESTING_FEATURES = (
    'allow_user_creation',
    'allow_user_dataset_purge',
    'brand',
    'enable_communication_server',
    'enable_openid',
    'enable_quotas',
    'enable_unique_workflow_defaults',
    'ftp_upload_site',
    'has_user_tool_filters',
    'message_box_visible',
    'message_box_content',
    'mailing_lists',
    'require_login',
    'server_startttime',
    'support_url',
    'terms_url',
    'wiki_url',
    'use_remote_user',
    'logo_src',
    'logo_url',
    'inactivity_box_content',
    'citation_url'
)


def assess_features(data):
    return {
        k: v for (k, v) in data.items()
        if k in INTERESTING_FEATURES
    }


def req_url_safe(url):
    try:
        r = requests.get(url, timeout=60, verify=False, headers=HEADERS)
    except requests.exceptions.ConnectTimeout:
        # If we cannot connect in time
        logging.debug("%s down, connect timeout", url)
        return None, 'connect'
    except requests.exceptions.SSLError as sle:
        # Or they have invalid SSL
        logging.debug("%s down, bad ssl: %s", url, sle)
        return None, 'ssl'
    except Exception as exc:
        # Or there is some OTHER exception
        logging.debug("%s down", url)
        return None, 'unk'
    # Ok, hopefully here means we've received a good response
    logging.debug("%s ok", url)
    return r, None


def req_json_safe(url):
    (r, error) = req_url_safe(url)
    if r is None:
        return r, error

    # Now we try decoding it as json.
    try:
        print(r)
        data = r.json()
    except simplejson.scanner.JSONDecodeError as jse:
        logging.debug("%s json_error: %s", url, jse)
        return None, 'json'

    return r, data


def no_api(url):
    # Ok, something went wrong, let's try the home page.
    (response, data) = req_url_safe(url)
    if response is None:
        # and something went wrong again, so we will call it down permanently.
        logging.info("%s down, bad ssl", response)
        return {
            'server': url,
            'responding': False,
            'galaxy': False,
        }

    if response.ok:
        if 'window.Galaxy' in response.text \
                or 'galaxyIcon_noText.png' in response.text \
                or 'iframe#galaxy_main' in response.text:
            # If, however, window.Galaxy is in the text of the returned page...
            return {
                'server': url,
                'response_time': response.elapsed.total_seconds(),
                'responding': True,
                'galaxy': True,
            }
    # Here we could not access the API and we also cannot access
    # the homepage.
    logging.info("%s inaccessible ok=%s galaxy in body=%s", url, response.ok, 'window.Galaxy' in response.text)
    return {
        'server': url,
        'response_time': response.elapsed.total_seconds(),
        'responding': True,
        'galaxy': False,
    }


def process_url(url):
    logging.info("Processing %s" % url)
    (response, data) = req_json_safe(url + '/api/configuration')
    if data is None:
        return no_api(url)

    # then we have a good contact for /api/configuration
    if 'version_major' not in data:
        return no_api(url)

    version = data['version_major']
    features = assess_features(response.json())
    # Ok, api is responding, but main page must be as well.
    (response_index, data_index) = req_url_safe(url)

    if response_index is not None and response_index.ok and 'window.Galaxy' in response_index.text:
        return {
            'server': url,
            'responding': True,
            'galaxy': True,

            'version': version,
            # how responsive is their server
            'response_time': response_index.elapsed.total_seconds(),
            # What interesting features does this galaxy have.
            'features': features,
        }

    if response_index:
        return {
            'server': url,
            'responding': True,
            'galaxy': False,
            'version': version,
            'response_time': response_index.elapsed.total_seconds(),
            'code': response_index.status_code,
            'features': features,
        }


def process_data(data):
    # Clone it
    server = dict(data)
    # Update it with results of processing
    results = process_url(data['url'].rstrip('/'))
    if results:
        server.update({'results': results})
    server.update({'_reqtime': datetime.datetime.utcnow().isoformat()})
    return server


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Fetch information about a list of Galaxy servers')
    parser.add_argument('servers', help='servers.csv file. First row ignored, columns: name,url,support,location,tags', default='servers.csv')
    parser.add_argument('--json_dir', help="Output directory for .json files", default='output')
    parser.add_argument('--influx', action='store_true', help='Enable influxdb output')
    parser.add_argument('--influx_db', default='test')
    parser.add_argument('--influx_host', default='influxdb')
    parser.add_argument('--influx_port', default=8086)

    args = parser.parse_args()

    data = []
    with open(args.servers, 'r') as csvfile:
        reader = csv.reader(csvfile)
        cols = next(reader)
        for row in reader:
            data.append({
                k: munge(v) for (k, v) in zip(cols, row)
            })
    data = [x for x in data if 'url' in x]

    # a thread pool that implements the process pool API.
    pool = multiprocessing.pool.ThreadPool(processes=CONCURRENCY)
    return_list = pool.map(process_data, data, chunksize=1)
    pool.close()
    today = datetime.datetime.now().strftime("%Y-%m-%d-%H")
    if not os.path.exists(args.json_dir):
        os.makedirs(args.json_dir)
    with open(os.path.join(args.json_dir, today + '.json'), 'w') as handle:
        json.dump(return_list, handle)

    if args.influx:
        from influxdb import InfluxDBClient
        client = InfluxDBClient(args.influx_host, args.influx_port, database=args.influx_db)

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
                    'response_time': server['results']['repsonse_time'],
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
