# adds the list of sounds from story_variables.json to config.toml to selectively download only relevant sounds
from pathlib import Path
import json,time,requests,re
import toml
DATA = 'https://raw.githubusercontent.com/ArknightsAssets/ArknightsGamedata/master/cn/gamedata/story/story_variables.json'
# DATA = 'https://raw.githubusercontent.com/Kengxxiao/ArknightsGameData/master/zh_CN/gamedata/story/story_variables.json'
dirpath = r'.\assets\torappu\dynamicassets\audio'
varsFile = Path('story_variables.json')
if not varsFile.exists() or time.time() - varsFile.stat().st_mtime > 60*60*24:
    with requests.get(DATA) as r:
        if r.status_code == 200:
            with varsFile.open('wb') as f:
                f.write(r.content)
with varsFile.open('rb') as f:
    vars = json.load(f)
usedFiles = set()
for v in vars.values():
    try:
        if (v.lower().startswith('sound_beta_2')):
            fpath = v.lower()
            if fpath.endswith('_loop'):
                # the .ab filenames do not include "_loop"
                fpath = fpath[:-5]
            # MH sound file paths are wrong (?) change CustomSE to AVG
            fpath = re.sub(r'/customse/act24side/', '/avg/act24side/', fpath)
            usedFiles.add(fpath)
    except:
        pass

result = set(p if p.split('/')[1] == 'music' else '/'.join(p.split('/')[:2]) for p in usedFiles)
# from pprint import pprint
# for entry in result:
    # print(f'"audio/{entry}",')
with open('config.toml', 'r') as file:
    data = toml.load(file)
data['path_whitelist'] += [f'audio/{r}' for r in result]
data['path_whitelist'] = list(set(data['path_whitelist']))
with open('config.toml', 'w') as file:
    toml.dump(data, file)
