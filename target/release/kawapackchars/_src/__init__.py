from os import PathLike
from typing import BinaryIO
from pathlib import Path
from warnings import warn
from shutil import rmtree
from UnityPy import Environment
from .unpack import extract_from_env
from .image import combine_textures, process_portraits


__all__ = ["extract", "extract_all", "DirPath"]


DirPath = str | PathLike[str]


def extract(data: BinaryIO, source_dir: DirPath, output_dir: DirPath) -> None:
    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        output_dir.mkdir()
    extract_from_env(Environment(data), Path(source_dir), output_dir)


def extract_all(
    input_dir: DirPath,
    output_dir: DirPath,
    reset: bool = True,
    portrait_dir: DirPath | None = None
) -> None:
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)

    if not input_dir.is_dir():
        warn("The input directory does not exist.", RuntimeWarning)
        return

    if reset and output_dir.is_dir():
        rmtree(output_dir)
    
    output_dir.mkdir()

    for path in input_dir.glob("**/*.ab"):
        if path.is_file():
            with open(path, "rb") as bundle:
                extract_from_env(Environment(bundle), path.parent, output_dir)

    combine_textures(output_dir)

    if portrait_dir:
        data_dir = output_dir / "torappu" / "dynamicassets" / "arts" / "charportraits" / "UIAtlasTextureRef"
        if (portrait_dir := Path(portrait_dir)).is_dir() and data_dir.is_dir():
            portrait_dir = Path(output_dir, *portrait_dir.parts[1:])
            process_portraits(portrait_dir, data_dir)
        else:
            warn("A portrait extraction directory was specified, but necessary files were not found.", RuntimeWarning)