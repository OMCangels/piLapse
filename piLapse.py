import datetime
import logging
import math
import multiprocessing as mp
import pathlib
import sys
import time
from typing import Optional

import click as click
import dateparser
import picamera
import tqdm as tqdm

import MyCamera
from UploadWorker import UploadWorker

_default_folder = "piLapse"


@click.command()
@click.option("-s", "--start", type=str, default="now", show_default=True, help="Time when recording starts.")
@click.option("-e", "--end", type=str, default="1h", show_default=True,
              help="Time when recording ends. If -n and -p are both specified then this will be ignored.")
@click.option("-n", "--num_images", type=click.IntRange(min=1), default=240, show_default=True,
              help="Number of images.")
@click.option("-p", "--pause", type=click.FloatRange(min=0.5), default=None, help="Pause between images in seconds.")
@click.option("-img", "--img_type", type=str, default="jpg", show_default=True, help="Image type.")
@click.option("-o", "--output_folder", type=str, default=f"~/{_default_folder}", show_default=True,
              help="Images are saved here.")
@click.option("-r", "--remote_path", type=str, default=None, show_default=True,
              help="Images are transmitted here via FTPS.\nLayout: hostname.subdomain.com/remote_path")
@click.option("-ru", "--remote_user", type=str, help="User for remote upload.")
@click.option("-rpw", "--remote_password", type=str, help="Password for remote upload.")
@click.option("-d", "--delete_local_files", type=bool, default=True, show_default=True,
              help="Delete local image files if remote path is specified.")
@click.option("-l", "--log_file_path", type=str, default="LOG.log", show_default=True,
              help="Filepath used for logging.")
@click.option("-ll", "--log_level_str", type=str, default="INFO", show_default=True,
              help="Log level used for logging. Possible:[NONE,DEBUG,INFO]")
def timelapse(start, end, num_images, pause, output_folder, delete_local_files, remote_path, remote_user,
              remote_password, img_type, log_file_path, log_level_str):
    start = dateparser.parse(start, settings={"PREFER_DATES_FROM": "future"})
    end = dateparser.parse(end, settings={"PREFER_DATES_FROM": "future"})

    if _is_default_param("output_folder"):
        output_folder = pathlib.Path.home().joinpath(_default_folder)
    else:
        output_folder = pathlib.Path(output_folder)
    timestamp = start.strftime('%Y-%m-%d_%H-%M-%S')
    output_folder = output_folder.joinpath(timestamp)
    output_folder.mkdir(parents=True, exist_ok=True)

    if log_level_str == "NONE":
        logging.basicConfig(level=logging.CRITICAL + 1)
    else:
        if _is_default_param("log_file_path"):
            log_file_path = str(output_folder.joinpath(log_file_path))
        if log_level_str == "DEBUG":
            log_level = logging.DEBUG
        else:
            log_level = logging.INFO
        logging.basicConfig(filename=log_file_path, level=log_level,
                            format='%(asctime)s:%(name)s:%(levelname)s:%(message)s')

    logging.info(f"Created output directory ({output_folder}")

    pause_ms = None if pause is None else int(pause * 1000)

    if pause_ms is None:
        pause_ms = math.floor(end.timestamp() - start.timestamp()) * 1000 / num_images
    else:
        if _is_default_param("num_images"):
            num_images = int(math.floor(end.timestamp() - start.timestamp()) * 1000 / pause_ms)
        else:
            duration_ms = pause_ms * (num_images - 1)
            end = dateparser.parse(f"{start.timestamp() + duration_ms / 1000}")

    if remote_path is None:
        delete_local_files = False
        sftp_dict = None
    else:
        remote_path = remote_path + "/" + timestamp
        path = remote_path.split("/", maxsplit=1)
        sftp_dict = {"host": path[0], "user": remote_user, "pw": remote_password, "path": path[1]}

    info = f"\nCONFIGURATION:\n" + f"Starting recording at: {start}\n" + \
           f"Ending recording at: {end}\n" + f"Number " + f"of images: {num_images}\n" + \
           f"Time between two images: {pause}s\n" + f"Image Type: {img_type}\n" + \
           f"Output folder: {output_folder}\n" + f"Remote path: {remote_path}\n" + \
           f"Delete local files: {delete_local_files}\n" + f"Logging path: {log_file_path}\n" + \
           f"Log level: {log_level_str}\n"
    print(info)
    logging.info(info)

    upload_worker = _start_upload_worker(delete_local_files, sftp_dict)
    try:
        _take_timelapse_images(start, end, num_images, img_type, pause_ms, output_folder, upload_worker)
    finally:
        if log_level_str != "NONE":
            upload_worker.add_work(log_file_path)
        _finish_upload_worker(upload_worker)

    if delete_local_files:
        output_folder.rmdir()


def _take_timelapse_images(start: datetime.datetime, end: datetime.datetime, num_images, img_type, pause_ms,
                           output_folder, upload_worker):
    num_zeros = math.ceil(math.log10(num_images))
    image_pattern = f"{output_folder}/image_{{counter:0{num_zeros}d}}_{{timestamp:%Y-%m-%d-%H-%M-%S}}.{img_type}"
    img_times = range(math.floor(start.timestamp() * 1000 + pause_ms), math.ceil(end.timestamp() * 1000 + 2 * pause_ms),
                      pause_ms)

    # TODO: remove
    """Just a fake to test"""
    picamera.PiCamera = MyCamera.MyCamera

    logger = logging.getLogger("Camera")
    img_counter = 0
    with picamera.PiCamera() as camera:
        print(f"Waiting until start ({start})")
        logger.info(f"Waiting until start ({start})")
        _wait_until(start.timestamp() * 1000, logger)
        for next_img_time_ms, filename in tqdm.tqdm(zip(img_times, camera.capture_continuous(output=image_pattern)),
                                                    initial=1, total=num_images):
            img_counter += 1
            logger.debug(f"Image taken ({filename})")
            _add_to_upload_worker(filename, upload_worker)
            if img_counter < num_images:
                _wait_until(next_img_time_ms, logger)
        logger.info("Finished taking images")


def _is_default_param(param):
    return click.get_current_context().get_parameter_source(param) == click.core.ParameterSource.DEFAULT


def _wait_until(time_ms, logger):
    now_ms = time.time_ns() / (10 ** 6)
    time_difference_to_next_image = (time_ms - now_ms) / 1000
    try:
        time.sleep(time_difference_to_next_image)
    except ValueError:
        print(f"Negative sleep time: {time_difference_to_next_image}", file=sys.stderr)
        logger.error(f"Negative sleep time: {time_difference_to_next_image}")


def _start_upload_worker(delete_local_files, ftps_dict) -> Optional[UploadWorker]:
    if ftps_dict is None:
        return None
    queue = mp.Queue()
    worker = UploadWorker(ftps_dict, queue, delete_local_files)
    worker.start()
    return worker


def _add_to_upload_worker(filename, upload_worker: Optional[UploadWorker]):
    if upload_worker is None:
        return
    upload_worker.add_work(filename)


def _finish_upload_worker(worker: UploadWorker):
    if worker is None:
        return
    worker.stop_worker()
    worker.join()


if __name__ == '__main__':
    timelapse()
