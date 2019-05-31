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
USER_AGENT = 'Galaxy Public Server Monitoring Bot (+https://github.com/martenson/public-galaxy-servers)'
HEADERS = {'User-Agent': USER_AGENT}
# Certificate verification is handled by requests and we want errors.
requests.packages.urllib3.disable_warnings()


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


def process_elems(elems, section=None):
    for e in elems:
        if e['model_class'] == 'ToolSection':
            for x in process_elems(e['elems'], section=e['name']):
                yield x
        elif e['model_class'][-4:] == 'Tool':
            i = e['id'].split('/')
            yield '/'.join(i)
            if len(i) > 2:
                i = '%s/%s' % (i[2], i[3])
            else:
                i = e['id']


def count_tools(data):
    return len(set(process_elems(data)))


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

    print(response_index, response_index.ok, 'window.Galaxy' in response_index.text)

    tools = 0
    lookslikegalaxy = False
    if response_index is not None and response_index.ok and ('window.Galaxy' in response_index.text or 'toolbox_in_panel' in response_index.text):
        lookslikegalaxy = True

        (response, data) = req_json_safe(url + '/api/tools')
        if data is not None:
            tools = count_tools(response.json())

    return {
        'server': url,
        'responding': True,
        'lookslikegalaxy': lookslikegalaxy,
        'version': version,
        # how responsive is their server
        'response_time': response_index.elapsed.total_seconds(),
        'code': response_index.status_code,
        # What interesting features does this galaxy have.
        'features': features,
        # Tools
        'tools': tools,
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
