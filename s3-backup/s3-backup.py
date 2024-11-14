import base64
import glob
import io
import logging
import os
import sys
from pathlib import Path

from PIL import Image

sys.path.append(os.path.dirname(os.getcwd()))

# pylint: disable=wrong-import-position
from common_funcs import CommonFuncs

logger = logging.getLogger()
logging.basicConfig(stream=sys.stdout, level=logging.INFO)

base_steps_client_names: list[str] = []

cf = CommonFuncs(
    logger,
    filename=str(os.path.basename(__file__)),
    json_paths=base_steps_client_names,
)


def main(
    source: str,
    dest: str,
):
    cf.info_log_starting()

    files: list[str] = [i for i in glob.glob(source + "/**/*", recursive=True) if os.path.isfile(i)]

    for source_path in files:
        with open(source_path, "r", encoding="utf-8") as f:
            source_file = f.read()
        try:
            img = Image.open(io.BytesIO(base64.decodebytes(bytes(source_file, "utf-8"))))
            logger.info(f"## Created image for source file: '{source_path}'")
            dest_path: str = f"{source_path.replace(source, dest, 1)}.png"
            Path(os.path.dirname(dest_path)).mkdir(exist_ok=True)
            img.save(dest_path)
            logger.info(f"## Saved image for source file: '{dest_path}'")
        except Exception as ex:
            logger.error(f"## Create image ERROR: '{ex}', for source file: '{source_path}'")

    cf.info_log_finished()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert all S3 objects from: base64 -> PNG, taking from a source directory "
        "and depositing in a destination directory."
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Specify the source directory, for the converting of all S3 objects from: base64 -> PNG, "
        "eg. '--source dir/foobar'.",
        type=str,
    )
    parser.add_argument(
        "--dest",
        required=True,
        help="Specify the destination directory, for the converting of all S3 objects from: base64 -> PNG, "
        "eg. '--dest dir/foobar'.",
        type=str,
    )
    args = parser.parse_args()
    main(
        source=args.source,
        dest=args.dest,
    )
