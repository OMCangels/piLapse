import datetime
import math
import multiprocessing as mp
import pathlib
import sys
import time
from typing import Optional

import click as click
import dateparser
import picamera

import MyCamera
from UploadWorker import UploadWorker


def is_default_param(param):
    return click.get_current_context().get_parameter_source(param) == click.core.ParameterSource.DEFAULT


default_folder = "piLapse"


@click.command()
@click.option("-s", "--start", type=str, default="now", show_default=True, help="Time when recording starts.")
@click.option("-e", "--end", type=str, default="1h", show_default=True,
              help="Time when recording ends. If -n and -p are both specified then this will be ignored.")
@click.option("-n", "--num_images", type=click.IntRange(min=1), default=240, show_default=True,
              help="Number of images.")
@click.option("-p", "--pause", type=click.FloatRange(min=0.5), default=None, help="Pause between images in seconds.")
@click.option("-img", "--img_type", type=str, default="jpg", show_default=True, help="Image type.")
@click.option("-o", "--output_folder", type=str, default=f"~/{default_folder}", show_default=True,
              help="Images are saved here.")
@click.option("-r", "--remote_path", type=str, default=None, show_default=True,
              help="Images are transmitted here via SFTP.\nLayout: hostname.subdomain.com/remote_path")
@click.option("-ru", "--remote_user", type=str, help="User for remote upload.")
@click.option("-rpw", "--remote_password", type=str, help="Password for remote upload.")
@click.option("-d", "--delete_local_files", type=bool, default=True, show_default=True,
              help="Delete local image files if remote path is specified.")
def main(start, end, num_images, pause, output_folder, delete_local_files, remote_path: str, remote_user,
         remote_password, img_type):
    start = dateparser.parse(start, settings={"PREFER_DATES_FROM": "future"})
    end = dateparser.parse(end, settings={"PREFER_DATES_FROM": "future"})

    if is_default_param("output_folder"):
        output_folder = pathlib.Path.home().joinpath(default_folder)
    else:
        output_folder = pathlib.Path(output_folder)
    timestamp = start.strftime('%Y-%m-%d_%H-%M-%S')
    output_folder = output_folder.joinpath(timestamp)

    pause_ms = None if pause is None else int(pause * 1000)

    if pause_ms is None:
        pause_ms = math.floor(end.timestamp() - start.timestamp()) * 1000 / num_images
    else:
        if is_default_param("num_images"):
            num_images = int(math.floor(end.timestamp() - start.timestamp()) * 1000 / pause_ms)
        else:
            duration_ms = pause_ms * num_images
            end = dateparser.parse(f"{start.timestamp() + duration_ms / 1000}")

    if remote_path is None:
        delete_local_files = False
        sftp_dict = None
    else:
        remote_path = remote_path + "/" + timestamp
        path = remote_path.split("/", maxsplit=1)
        sftp_dict = {"host": path[0], "user": remote_user, "pw": remote_password, "path": path[1]}

    print(f"\nCONFIGURATION:")
    print(f"Starting recording at: {start}")
    print(f"Ending recording at: {end}")
    print(f"Number of images: {num_images}")
    print(f"Time between two images: {pause}s")
    print(f"Image Type: {img_type}")
    print(f"Output folder: {output_folder}")
    print(f"Remote path: {remote_path}")
    print(f"Delete local files: {delete_local_files}")
    print(f"\nTaking Timelapse")

    output_folder.mkdir(parents=True, exist_ok=True)

    take_timelapse_images(start, end, num_images, img_type, pause_ms, output_folder, delete_local_files, sftp_dict)


def wait_until(time_ms):
    now_ms = time.time_ns() / (10 ** 6)
    time_difference_to_next_image = (time_ms - now_ms) / 1000
    try:
        time.sleep(time_difference_to_next_image)
    except ValueError:
        print(f"Negative sleep time: {time_difference_to_next_image}", file=sys.stderr)


def start_upload_worker(delete_local_files, sftp_dict) -> Optional[UploadWorker]:
    if sftp_dict is None:
        return None
    queue = mp.Queue()
    host, user, pw, remote_path = sftp_dict["host"], sftp_dict["user"], sftp_dict["pw"], sftp_dict["path"]
    worker = UploadWorker(host, remote_path, user, pw, queue, delete_local_files)
    worker.start()
    return worker


def add_to_upload_worker(filename, upload_worker: Optional[UploadWorker]):
    if upload_worker is None:
        return
    upload_worker.add_work(filename)


def finish_upload_worker(worker):
    if worker is None:
        return
    worker.stop_worker()
    worker.join()


def take_timelapse_images(start: datetime.datetime, end: datetime.datetime, num_images, img_type, pause_ms,
                          output_folder, delete_local_files, sftp_dict):
    num_zeros = math.ceil(math.log10(num_images))
    image_pattern = f"{output_folder}/image_{{counter:0{num_zeros}d}}_{{timestamp:%Y-%m-%d-%H-%M-%S}}.{img_type}"
    img_times = range(math.floor(start.timestamp() * 1000 + pause_ms), math.ceil(end.timestamp() * 1000 + pause_ms),
                      pause_ms)

    upload_worker = start_upload_worker(delete_local_files, sftp_dict)

    # TODO: remove
    """Just a fake to test"""
    picamera.PiCamera = MyCamera.MyCamera

    try:
        with picamera.PiCamera() as camera:
            print(f"Waiting until start: {start}")
            wait_until(start.timestamp() * 1000)
            for img_time, filename in zip(img_times, camera.capture_continuous(output=image_pattern)):
                # TODO: use tqdm with img_times to provide %
                # TODO: Log image taken
                add_to_upload_worker(filename, upload_worker)
                wait_until(img_time)
    finally:
        finish_upload_worker(upload_worker)


if __name__ == '__main__':
    main()
