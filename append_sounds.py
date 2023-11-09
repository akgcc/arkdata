# adds the list of sounds from story_variables.json to config.toml to selectively download only relevant sounds
from pathlib import Path
import json,time,requests,re
import toml
dirpath = r'.\assets\torappu\dynamicassets\audio'
varsFile = Path('story_variables.json')
if not varsFile.exists() or time.time() - varsFile.stat().st_mtime > 60*60*24:
    with requests.get('https://raw.githubusercontent.com/Kengxxiao/ArknightsGameData/master/zh_CN/gamedata/story/story_variables.json') as r:
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
            # MH sound file paths are wrong (?) change CustomSE to AVG
            fpath = re.sub(r'/customse/act24side/', '/avg/act24side/', fpath)
            usedFiles.add(fpath)
    except:
        pass

result = set(p if p.split('/')[1:2][0] == 'music' else '/'.join(p.split('/')[:2]) for p in usedFiles)
# from pprint import pprint
# for entry in result:
    # print(f'"audio/{entry}",')
with open('config.toml', 'r') as file:
    data = toml.load(file)
data['path_whitelist'] += [f'audio/{r}' for r in list(result)[:1]]
data['path_whitelist'] = list(set(data['path_whitelist']))
with open('config.toml', 'w') as file:
    toml.dump(data, file)