from UnityPy import Environment
from UnityPy.classes import Object, Sprite, Texture2D, TextAsset, AudioClip, MonoBehaviour
from UnityPy.enums import ClassIDType as Obj
from pathlib import Path
import json
import bson
from Crypto.Cipher import AES
from fsb5 import FSB5
from warnings import warn
from PIL import Image

def get_target_path(obj: Object, source_dir: Path, output_dir: Path) -> Path:
    if obj.container:
        source_dir = Path(*Path(obj.container).parts[1:-1])

    if isinstance(obj, MonoBehaviour) and (script := obj.m_Script):
        return output_dir / source_dir / script.read().name

    assert isinstance(obj.name, str)
    return output_dir / source_dir / obj.name


# Some assets have identical file paths, so unique
# file names are generated to prevent overwriting data.
def get_available_path(path: Path) -> Path:
    if path.is_file():
        path = path.with_stem(path.stem + "_1")
        index = 1
        while path.is_file():
            index += 1
            new_name = f"_{index}".join(path.stem.rsplit(f"_{index-1}", 1))
            path = path.with_stem(new_name)
    return path


def write_bytes(data: bytes, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def write_object(data: object, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_suffix(".json"), "w", encoding="utf8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def write_binary_object(data: bytes, path: Path) -> None:
    try:
        # BSON decoding fails if data is JSON-encoded BSON instead of plain BSON
        decoded = bson.decode(data)
        write_object(decoded, path)
    except:
        write_object(json.loads(data), path)


def decrypt_textasset(stream: bytes) -> bytes:
    def unpad(data: bytes) -> bytes:
        end_index = len(data) - data[-1]
        return data[:end_index]

    CHAT_MASK = bytes.fromhex('554954704169383270484157776e7a7148524d4377506f6e4a4c49423357436c').decode()

    aes_key = CHAT_MASK[:16].encode()
    aes_iv = bytearray(
        buffer_bit ^ mask_bit
        for (buffer_bit, mask_bit) in zip(stream[:16], CHAT_MASK[16:].encode())
    )

    decrypted = (
        AES.new(aes_key, AES.MODE_CBC, aes_iv)
        .decrypt(stream[16:])
    )

    return unpad(decrypted)


def export(obj: Object, target_path: Path) -> None:
    match obj:
        case Sprite() | Texture2D():
            if (img := obj.image).width > 0:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                img.save(target_path.with_suffix(".png"))

        case TextAsset():
            target_path_str = target_path.as_posix()
            data = bytes(obj.script)
            if "gamedata/story" in target_path_str:
                # Story text is unencrypted, so the data can be saved without further changes
                write_bytes(data, target_path.with_suffix(".txt"))
            elif "gamedata/levels/" in target_path_str:
                try:
                    # Level data is only encrypted for US server. Attempts to decrypt CN data will fail.
                    data = decrypt_textasset(data)
                    write_binary_object(data, target_path)
                except:
                    try:
                        # Extraneous starting bytes must be removed before attempting to parse as BSON
                        write_binary_object(data[128:], target_path)
                    except:
                        warn(f"Failed to save data to {target_path}", RuntimeWarning)
                        # if "obt/memory" in target_path_str:
                        #     data = decrypt_textasset(data[(256 + len(data) % 16):])
                        #     ...
                        # write_bytes(data, target_path)
            else:
                try:
                    # Decryption will fail if the data is not actually encrypted
                    # Extraneous starting bytes must be removed before attempting decryption
                    data = decrypt_textasset(data[128:])
                    write_binary_object(data, target_path)
                except:
                    try:
                        write_object(json.loads(data), target_path)
                    except:
                        write_bytes(data, target_path)

        case AudioClip():
            fsb = FSB5(obj.m_AudioData)
            assert len(fsb.samples) == 1
            target_path = target_path.with_suffix("." + fsb.get_sample_extension())

            try:
                # Audio clip conversion will fail if DLLs needed by fsb5
                # (libogg, libvorbis, libvorbisenc, libvorbisfile) cannot be found
                # or the CRC32 value associated with the file format is incorrect.
                sample = fsb.rebuild_sample(fsb.samples[0])
                write_bytes(sample, target_path)
            except:
                warn(f"Failed to save audio clip to {target_path}", RuntimeWarning)

        case MonoBehaviour():
            if obj.name:
                tree = obj.read_typetree()
                target_path = get_available_path(
                    target_path.joinpath(obj.name).with_suffix(".json")
                )
                write_object(tree, target_path)

def extract_from_env(env: Environment, source_dir: Path, output_dir: Path):
    source_path_parts = set(source_dir.parts)
    if "chararts" in source_path_parts or "skinpack" in source_path_parts:
        for object in env.objects:
            if object.type == Obj.Texture2D:
                resource = object.read()
                if isinstance(resource, Texture2D) and resource.m_Width > 512 and resource.m_Height > 512:
                    target_path = get_target_path(resource, source_dir, output_dir)
                    export(env, resource, target_path)
    elif "avg" in source_path_parts and "characters" in source_path_parts:
        extract_character_with_faces(env, source_dir, output_dir)
    else:
        for object in env.objects:
            if object.type in {Obj.Sprite, Obj.Texture2D, Obj.TextAsset, Obj.AudioClip, Obj.MonoBehaviour}:
                resource = object.read()
                if isinstance(resource, Object):
                    target_path = get_target_path(resource, source_dir, output_dir)
                    export(resource, target_path)
                    
def extract_character_with_faces(env: Environment, source_dir: Path, output_dir: Path):
    path_map = {}
    groupData = {}
    for object in env.objects:
        if object.type in {Obj.Sprite, Obj.Texture2D, Obj.MonoBehaviour}:
            resource = object.read()
            if not isinstance(resource, Object):
                continue
            if object.type in {Obj.Sprite, Obj.Texture2D}:
                path_map[resource.path_id] = resource
            elif object.type == Obj.MonoBehaviour and (script := resource.m_Script):
                dname = script.read().name
                if dname == 'AVGCharacterSpriteHubGroup':
                    tree = resource.read_typetree()
                    groupData = tree
                elif dname == 'AVGCharacterSpriteHub':
                    tree = resource.read_typetree()
                    groupData = tree
                    groupData['spriteGroups'] = [{'sprites':groupData['sprites'],'facePos':groupData.get('facePos',groupData['FacePos']), 'faceSize': groupData.get('faceSize',groupData['FaceSize'])}]
    for bodyNum,body in enumerate(groupData['spriteGroups']):
        face_rect = {
            'x': int(body['facePos']['x']),
            'y': int(body['facePos']['y']),
            'w': int(body['faceSize']['x']),
            'h': int(body['faceSize']['y'])
        }

        isFullImages = not (face_rect['x'] >= 0 and face_rect['y'] >= 0)
        
        if not isFullImages:
            # load base image (last one in sprites) and apply alpha
            base = combine_alpha(path_map[body['sprites'][-1]['sprite']['m_PathID']].image, path_map[body['sprites'][-1]['alphaTex']['m_PathID']].image)
        for faceNum,face in enumerate(body['sprites']):
            dest_path = (output_dir / source_dir / f'{Path(next(iter(env.container.keys()))).stem}#{faceNum+1}${bodyNum+1}').with_suffix(".png")
            face_img = combine_alpha(path_map[face['sprite']['m_PathID']].image,path_map[face['alphaTex']['m_PathID']].image)
            if isFullImages or face.get('isWholeBody',False):
                face_img.save(dest_path)
                face_img.close()
                continue
            if faceNum == len(body['sprites'])-1:
                # for non-full images, the last sprite is identical to the first, so don't save it.
                continue
            face_img = face_img.resize((face_rect['w'], face_rect['h']))
            complete_img = base.copy()
            complete_img.paste(face_img, (face_rect['x'], face_rect['y']))
            complete_img.save(dest_path)
            face_img.close()
            complete_img.close()
        if not isFullImages:
            base.close()
def combine_alpha(img_data, alpha_data):
    base = img_data.convert("RGBA")
    alpha = alpha_data.convert("L")
    assert(base.size == alpha.size)
    base.putalpha(alpha)
    alpha.close()
    return base