from pathlib import Path
import re
import json
import numpy as np
import imagesize
import cv2
from anime_face_detector import create_detector
detector = create_detector('yolov3',device='cpu')

DEFAULT = {"x": -205, "y": 0, "s": .5, "a": 0}
AVATAR_SIZE = 96
AVG_SIZE = 1024
# SCALE_LIMITS = (.125, 1)
SCALE_LIMITS = (-999,999)
re_chars = re.compile(b'name\d*\s*=\s*"?((?<=")[^"]*)',re.I)
OVERWRITE_ALL_THUMBS = False # if true will replace all thumbs IMAGES (will not redo finding the coords of thumbs), you probably NEVER want to do this, and instead want to use OVERWRITE_MANUAL_THUMBS
OVERWRITE_MANUAL_THUMBS = False # if true will overwrite all thumbs defined in manual_coords.json, you must do this if you edit existing coords.

coordsFile = Path('./cropper_data/auto_coords.json')
outputCoords = Path('./cropper_data/avatar_coords.json')
failedCoords = Path('./cropper_data/failed_coords.json')
manCoords = Path('./cropper_data/manual_coords.json')
outputDir = Path('./thumbs')
storyDir = Path('./ArknightsGameData/cn/gamedata/story')
avgDir = Path('./assets/avg/characters')
# aceshipDir = Path(r'.\characters_aceship')

# see bucket_by_substring, these exceptions are for avatars where the same pose has in actuality a different pose, making the face not line up with other faces in the same "pose group", see char_115_headbr_9 for an example.
# this dict is in the format id: [[list of faces],[second list of faces if multiple distinct exceptions]]
POSE_EXCEPTIONS = {
'char_115_headbr_9':[['10','11']],
'avg_npc_143': [['2']],
'avg_npc_192_1': [['8']],
'char_012_misa_1': [['5']],
'avg_4142_laios_1': [['4']],
}

SPLIT_REGEX = re.compile(r'^(.*?)(?:#(\d+))?(?:\$(\d+))?$')
# Function to calculate the Euclidean distance from the origin (0, 0) for a given coordinate
def distance_from_origin(coord):
    return (coord['x'] ** 2 + coord['y'] ** 2) ** 0.5

# Function to calculate the median coordinate
def calculate_median_coordinate(coordinatesList):
    # Sort the coordinates list based on the Euclidean distance from the origin
    sorted_coordinates = sorted(coordinatesList, key=lambda coord: distance_from_origin(coord))

    # Find the middle index
    middle_index = len(sorted_coordinates) // 2

    # Return the coordinate at the middle index
    return sorted_coordinates[middle_index]
def bucket_by_substring(obj, failures):
    buckets = {}

    for key in obj:
        match = SPLIT_REGEX.match(key)
        id_, face, pose = match.groups()
        uid = f"{id_}${pose}"
        if id_ in POSE_EXCEPTIONS:
            for i,faces in enumerate(POSE_EXCEPTIONS[id_]):
                if face in faces:
                    uid = f"{id_}${pose}#{i}"
        if uid in buckets:
            buckets[uid].append(key)
        else:
            buckets[uid] = [key]
            
    # add items from failures into their bucket if it exists (and del them from failures afterwards)
    # keys_to_remove = []
    for key in failures:
        match = SPLIT_REGEX.match(key)
        id_, face, pose = match.groups()
        uid = f"{id_}${pose}"
        if id_ in POSE_EXCEPTIONS:
            for i,faces in enumerate(POSE_EXCEPTIONS[id_]):
                if face in faces:
                    uid = f"{id_}${pose}#{i}"
        if uid in buckets:
            buckets[uid].append(key)
            # keys_to_remove.append(key)
    # for key in keys_to_remove:
        # del failures[key]
    return buckets
def normalize_buckets(buckets, coords, failures):
    # sets all coords in a bucket to the median of that bucket.
    # this ensures faces will line up
    for _,v in buckets.items():
        valid_coords = [coords[x] for x in v if x not in failures.keys()]
        if len(valid_coords) == 0:
            # no valid coords in this bucket, skip it
            continue
        med = calculate_median_coordinate(valid_coords)
        for key in v:
            coords[key] = med
            if key in failures:
                del failures[key]


def get_chars(path):
    chars = set()
    with path.open('rb') as f:
        for line in f.readlines():
            if line.lower().startswith((b'[character(',b'[charslot(')):
                for c in re_chars.findall(line):
                    cname = c.decode("utf8").strip()
                    if cname not in ['middle','right','left','char_empty_b','$ill_amiya_normal']:
                        chars.add(cname)
    return chars
chars = set()
i = 0
for p in storyDir.glob('**/*.txt'):
    chars = chars.union(get_chars(p))
chars.discard('')

# Function to check if the image is corrupted
def is_corrupted(image_path):
    try:
        with open(image_path, 'rb') as f:
            byte = f.read(1)
            while byte:
                byte = f.read(1)
    except Exception as e:
        return True
    return False
def is_valid_avg(image_path, aceship = False):
    width, height = imagesize.get(str(image_path))
    if aceship:
        return width == AVG_SIZE and height == AVG_SIZE
    return width > 0 and height > 0
def generate_paths(id,face,body):
    if face == '1' and body == '1':
        yield f'{id}.png'  # Only ID
    if body == '1':
        yield f'{id}#{face}.png'  # ID and Face
        # yield f'{id}_{face}.png'  # ID and Face (underscore)
    if face == '1':
        yield f'{id}${body}.png'  # ID and Body
    yield f'{id}#{face}${body}.png'  # ID, Face, and Body
    yield f'{id}#{face}${body}.webp'  # webp for arkwaifu

# print(chars)
all_chars = []
print(len(chars),'images found')
to_download = [] # removed ability to dl missing images from arkwaifu, this is defunct
# also removed the local copy of aceship images, you won't be able to rebuild the avatar versions of aceship exclusives.
for c in list(chars):
    for char in SPLIT_REGEX.findall(c):
        id, face, body = char
        face = (face or '1').lstrip('0')
        body = (body or '1').lstrip('0')
        fullpath = f'{id}#{face}${body}.png'
        passed = False
        for path in generate_paths(id,face,body):
            if (avgDir / path).exists() and is_valid_avg(avgDir / path):
                all_chars.append((f'{id}#{face}${body}',avgDir / path))
                passed = True
        if not passed:
            print(char,'doesnt exist','dling',c)
            to_download.append(f'{id}#{face}${body}')
        
        # print(f'{char}.png',(avgDir / f'{id}.png').exists())
        

# now with all images downloaded, detect faces:
def get_coords(path,debug = False):
    # print('opening image at ',path)
    if not path.exists():
        return None
    image = cv2.imread(str(path))
    preds = detector(image)
    if not preds:
        return None
    # print(preds[0]['bbox'])
    if debug:
        print(preds)
    bbox = preds[0]['bbox']
    # bbox is x1 y1 x2 y2 
    # print(bbox[2]-bbox[0], bbox[3]-bbox[1])
    if debug:
        cv2.rectangle(image, (int(bbox[0]),int(bbox[1])), (int(bbox[2]),int(bbox[3])), (0,255,0),2)

    x = bbox[0]
    y = bbox[1]
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    side = min(width,height)
    if width > height:
        x+= (width-height)//2
    else:
        y+= (height-width)//2
    x = int(x)
    y = int(y)
    if debug:
        cv2.rectangle(image, (int(x),int(y)),(int(x)+int(side),int(y)+int(side)), (0,0,255),2)
    s_r = AVATAR_SIZE/side
    s = min(max(SCALE_LIMITS[0], s_r), SCALE_LIMITS[1]);
    s*=.65 # zoom out
    # s-= .3
    adjust = (s_r*side - s*side)
    if debug:
        # print({'x':int((-x+adjust/2)*s),'y':int((-y+adjust/2)*s),'s':s})
        # print({'x':int(-x*s+adjust/2),'y':int(-y*s+adjust/2),'s':s})
        cv2.imshow('out',image)
        cv2.waitKey(0)
    return {'x':int(-x*s+adjust/2),'y':int(-y*s+adjust/2),'s':round(s,2)}
def crop_image(image, coords):
    x, y, s = -coords['x'], -coords['y'], coords['s']
    scaled_image = cv2.resize(image, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    scaled_image = np.pad(scaled_image, ((max(-y, 0), 0), (max(-x, 0), 0), (0, 0)), mode='constant', constant_values=0)
    x = max(x,0)
    y = max(y,0)
    cropped_image = scaled_image[y:y+96, x:x+96]
    return cropped_image
with open(coordsFile,'r') as f:
    avatar_coords = json.load(f)
with open(failedCoords,'r') as f:
    failed_coords = json.load(f)
with open(manCoords,'r') as f:
    manual_coords = json.load(f)
manual_coords = {k: v for k, v in manual_coords.items() if v}
for k, v in manual_coords.items():
    failed_coords.pop(k,None)
manual_coords_buckets = bucket_by_substring(manual_coords,failed_coords)
for name,path in all_chars:
    # print(get_coords(avgDir / 'avg_npc_034_14.png',True))
    # print(name,get_coords(path,True))
    if (name not in avatar_coords) and (name not in manual_coords):
        # print('calcing bbox',name,path)
        # bbox = None
        bbox = get_coords(path)
        if bbox:
            avatar_coords[name] = bbox
            failed_coords.pop(name,None)
        else:
            failed_coords[name] = str(path)
    
    id,face,pose = SPLIT_REGEX.match(name).groups()
    if id in manual_coords_buckets:
        # add coords to manual_coords by copying sibling coords
        manual_coords[name] = manual_coords_buckets[id]

# bucket_by_substring will also bucket failures if possible
buckets = bucket_by_substring(avatar_coords,failed_coords)
# normalize_buckets will remove keys from failed_coords if they were successfully bucketed.
normalize_buckets(buckets, avatar_coords, failed_coords)
for name,path in all_chars:
    outpath = outputDir / f'{name}.webp'
    if (name in avatar_coords or name in manual_coords):
        if (not outpath.exists()) or OVERWRITE_ALL_THUMBS or (OVERWRITE_MANUAL_THUMBS and (name in manual_coords)):
            print('writing thumb to',outpath)
            # print('writing thumb to',outpath,'from',path,'cropped to',manual_coords.get(name) or avatar_coords[name])
            img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
            # use coords given in manual_coords FIRST in case some auto coords needed to be modified.
            cropped_image = crop_image(img, manual_coords.get(name) or avatar_coords[name])
            if cropped_image is None or cropped_image.size == 0 or min(cropped_image.shape[:2]) == 0:
                # coords failed, mark as such and skip:
                failed_coords[name] = str(path)
                avatar_coords.pop(name,None)
            else:
                cv2.imwrite(str(outpath).lower(), cropped_image)

    
with open(failedCoords,'w') as f:
    json.dump(failed_coords,f)
with open(coordsFile,'w') as f:
    json.dump(avatar_coords,f)
avatar_coords.update(manual_coords)
with open(outputCoords,'w') as f:
    json.dump(avatar_coords,f)
    
print(len(failed_coords),'failures, fix manually.')