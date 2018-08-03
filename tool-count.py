import json
import sys


data = json.load(sys.stdin)

seen_before = {}


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

            n = '%s|%s' % (i, e['name'])

            if n not in seen_before:
                seen_before[n] = []
            seen_before[n].append(section)


data = list(process_elems(data))
tools = list(data)
uniq_tools = set(tools)

print('galaxy.tools,server=%s count=%s,uniq=%s' %
      (sys.argv[1], len(tools), len(uniq_tools)))
