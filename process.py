#!/usr/bin/env python
import multiprocessing.pool
import csv
import datetime
import simplejson
import json
import requests
import logging
from influxdb import InfluxDBClient
logging.basicConfig(level=logging.DEBUG)
CONCURRENCY = 20
influxdb_enabled = True


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
        r = requests.get(url, timeout=30)
    except requests.exceptions.ConnectTimeout:
        # If we cannot connect in time
        logging.debug("%s down, connect timeout", url)
        return None, 'connect'
    except requests.exceptions.SSLError as sle:
        # Or they have invalid SSL
        logging.debug("%s down, bad ssl", url)
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
    server.update({'results': process_url(data['url'].rstrip('/'))})
    server.update({'_reqtime': datetime.datetime.utcnow().isoformat()})
    return server


if __name__ == '__main__':
    data = []
    with open('servers.csv', 'r') as csvfile:
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
    with open(today + '.json', 'w') as handle:
        json.dump(return_list, handle)


    if influxdb_enabled:
        client = InfluxDBClient('influxdb', 8086, database='test')

        measurements = []
        for server in return_list:
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
                    'response_time': server['results'].get('response_time', float(40)),
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
