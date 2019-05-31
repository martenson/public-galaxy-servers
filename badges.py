#!/usr/bin/env python
import cgi
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time


INPUT_DIR = sys.argv[1]
OUTPUT_DIR = sys.argv[2]
# A dir for storing static copies of the badges so we don't hit their API incessantly.
STATIC_DIR = os.path.join(OUTPUT_DIR, '.static')

if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)

NOW = datetime.datetime.now()
FMT = "%Y-%m-%d-%H"

buckets = (
    (99, 'green'),
    (95, 'yellow'),
    (85, 'orange'),
    (0, 'red'),
)


def get_color(uptime):
    for (target, color) in buckets:
        if uptime >= target:
            return color
    return 'red'


results = {}
found_files = 0

# Last 24 hours * 30 days
for t in range(-24 * 30, 0):
    then = NOW + datetime.timedelta(hours=t)
    path = os.path.join(INPUT_DIR, then.strftime(FMT) + '.json')

    if not os.path.exists(path):
        continue

    with open(path, 'r') as handle:
        try:
            data = json.load(handle)
        except ValueError:
            print("Could not load %s" % path)
    found_files += 1

    for server in data:
        if server['name'] not in results:
            results[server['name']] = []

        if 'results' not in server:
            continue

        results[server['name']].append(
            server['results']['galaxy'] or 'features' in server['results']
        )

html_data = """
<html><head></head>
<body>
<h1>Galaxy Uptime</h1>
<p>
These badges are the results of regularly checking in with your Galaxy
instance. The numbers may not be accurate (this month, 2017-10) due to changes
in the script as we identified cases where we incorrectly identified your
server as offline. Note that even then, the uptime number is reflective only of
our hourly check-ins with your server.
</p>
<table>
"""

for server in sorted(results):
    # Calculate uptime
    uptime = 100 * float(sum(results[server])) / found_files
    # Safe filename for storing the image as.
    filename = re.sub('[^A-Za-z0-9_ @]', '_', server) + '.svg'
    # Copy the appropriate image / download if not existing.
    src_img = os.path.join(STATIC_DIR, '%0.2f.svg' % uptime)
    dst_img = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(src_img):
        # Download the missing image
        cmd = [
            'wget', 'https://img.shields.io/badge/uptime-%0.2f%%25-%s.svg' % (uptime, get_color(uptime)),
            '--quiet', '-O', src_img
        ]
        subprocess.check_call(cmd)
        # Be nice to their servers
        time.sleep(1.5)

    # Ok, we've got their image, copy it over to somewhere named based on their server.
    shutil.copy(src_img, dst_img)
    html_data += "<tr><td>" + cgi.escape(server) + "</td><td><img src='" + filename + "' /></td></tr>"

html_data += """
</table></body></html>
"""

with open(os.path.join(OUTPUT_DIR, 'index.html'), 'w') as handle:
    handle.write(html_data)
