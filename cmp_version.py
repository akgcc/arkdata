import json
from urllib import request
from pathlib import Path
url = "https://ak-conf.hypergryph.com/config/prod/official/Android/version"
server = 'CN'
versionCache = Path('./cache/versions.json')

# Make the GET request
response = request.urlopen(url)
content = response.read()

# Decode the JSON content
json_data = json.loads(content.decode("utf-8"))

with versionCache.open('r') as file:
    json_data_from_file = json.load(file)
if json_data['resVersion'] == json_data_from_file[server]['resource'] and json_data['clientVersion'] == json_data_from_file[server]['client']:
    exit(1)
exit(0)