import glob
import datetime as dt
import json


servers = {}

previous = {}
dates = []
names = []
versions = []

for i in sorted(glob.glob("json/*-00.json")):
    with open(i, 'r') as handle:
        data = json.load(handle)

    date = i.strip('.json').strip('/')
    dates.append(date)

    for server in data:
        name = server['name']
        version = server.get('results', {}).get('version', None)

        if name not in names:
            names.append(name)

        if version:
            previous[name] = version
            if version not in versions:
                versions.append(version)
        else:
            if name in previous:
                version = previous[name]

        servers[(name, date)] = version


clean = {}
for date in dates:
    clean[date] = {k: 0 for k in versions}

    for name in names:
        version = servers.get((name, date), None)
        if not version:
            continue

        clean[date][version] += 1

versions = sorted(versions)

# Header
with open('releases.tsv', 'w') as handle:
    handle.write('#\trelease_' + '\trelease_'.join(versions))
    handle.write('\n')

    # By line
    for date in sorted(clean.keys()):
        q = [date[0:-3]]

        for v in versions:
            q.append(str(clean[date].get(v, '')))

        handle.write('\t'.join(q))
        handle.write('\n')


clean2 = {}
for date in dates:
    clean2[date] = {'supported': 0, 'unsupported': 0}
    d = dt.datetime.strptime(date[0:-3], '%Y-%m-%d')

    for name in names:
        version = servers.get((name, date), None)

        if not version:
            continue

        vd = dt.datetime.strptime(version, '%y.%m')
        if (d - vd) > dt.timedelta(days=365):
            key = 'unsupported'
        else:
            key = 'supported'
        # print(d, vd, d - vd, (d - vd) > dt.timedelta(days=365), key)

        clean2[date][key] += 1

with open('releases_supported.tsv', 'w') as handle:
    handle.write('#\tsupported\tunsupported\n')

    # By line
    for date in sorted(clean2.keys()):
        q = [date[0:-3]]
        d = dt.datetime.strptime(date[0:-3], '%Y-%m-%d')

        q.append(str(clean2[date].get('supported', 0)))
        q.append(str(clean2[date].get('unsupported', 0)))

        handle.write('\t'.join(q))
        handle.write('\n')
