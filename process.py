#!/usr/bin/env python
import csv
import datetime
import simplejson
import json
import requests
import logging
logging.basicConfig(level=logging.INFO)


def munge(value):
    if value == 'yes':
        return True
    elif value == 'no':
        return False
    elif len(value.strip()) == 0:
        return None
    else:
        return value

data = []
with open('servers.csv', 'rb') as csvfile:
    reader = csv.reader(csvfile)
    cols = next(reader)
    for row in reader:
        data.append({
            k: munge(v) for (k, v) in zip(cols, row)
        })

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


responses = []
for row in data:
    if 'url' not in row:
        loging.info("missing url for entry")
        continue;
    url = row['url'].rstrip('/')

    try:
        r = requests.get(url + '/api/configuration', timeout=30)
        version = r.json()['version_major']
        # But this doesn't completely mean it is up. The UI needs to be loading.
        r_index = requests.get(url, timeout=30)
        if r_index.ok and 'window.Galaxy' in r_index.text:
            responses.append({
                'server': url,
                'version': version,
                # how responsive is their server
                'response_time': r.elapsed.total_seconds(),
                # Error code, should be 200, but may be interesting things here as well?
                'code': r.status_code,
                # What interesting features does this galaxy have.
                'features': assess_features(r.json()),
                # Can we access the home page / window.Galaxy is in there.
                'homepage': True,
            })
            logging.info("%s up", url)
        else:
            logging.info("%s up, but ok=%s galaxy in body=%s", url, r.ok, 'window.Galaxy' in r_index.text)
            responses.append({
                'server': url,
                'version': version,
                'response_time': r.elapsed.total_seconds(),
                'code': r.status_code,
                'features': assess_features(r.json()),
                # Here we cannot access home page. E.g. remote_user
                'homepage': False,
            })
    except requests.exceptions.ConnectTimeout:
        responses.append({'server': url})
    except simplejson.scanner.JSONDecodeError:
        # ok, wasn't json. Was this an error?
        try:
            r_index = requests.get(url, timeout=30)
        except requests.exceptions.SSLError:
            logging.info("%s down, bad ssl", url)
            responses.append({'server': url})
            continue

        if r_index.ok and 'window.Galaxy' in r_index.text:
            responses.append({
                'server': url,
                'version': None,
                'response_time': r.elapsed.total_seconds(),
                'code': r.status_code,
                'features': {},
                'homepage': True,
            })
            logging.info("%s up", url)
        else:
            # Here we could not access the API and we also cannot access
            # the homepage.
            logging.info("%s inaccessible ok=%s galaxy in body=%s", url, r.ok, 'window.Galaxy' in r_index.text)
            responses.append({
                'server': url,
                'version': None,
                'response_time': r.elapsed.total_seconds(),
                'code': r.status_code,
                'features': {},
                'homepage': False,
            })
    except requests.exceptions.SSLError:
        logging.info("%s down, bad ssl", url)
        responses.append({'server': url})
    except Exception as exc:
        responses.append({'server': url})
        logging.info("%s down", url)

today = datetime.datetime.now().strftime("%Y-%m-%d-%H")
with open(today + '.json', 'w') as handle:
    json.dump(responses, handle)
