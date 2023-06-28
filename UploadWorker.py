import ftplib
import logging
import pathlib
import sys
from multiprocessing import Process, Queue


class UploadWorker(Process):

    def __init__(self, ftps_dict, queue: Queue, delete_local, termination_symbol=None):
        self._upload_queue = queue
        self._delete_local = delete_local
        self._termination_symbol = termination_symbol
        self._ftps_dict = ftps_dict
        self._ftp = None
        self._logger = logging.getLogger(__name__)
        super().__init__(target=self.upload_files)

    def upload_files(self):
        self._logger.info("Worker started")
        self._start_ftps_connection()
        while True:
            item = self._upload_queue.get()
            if item == self._termination_symbol:
                if self._upload_queue.empty():
                    return
                else:
                    self._upload_queue.put(self._termination_symbol)
            else:
                file = pathlib.Path(item)
                try:
                    self._upload(file)
                    if self._delete_local:
                        self._delete_local_file(file)
                except ftplib.all_errors as e:
                    self._logger.error(f"Error uploading local file ({file})", exc_info=True)
                    print(f"Error uploading: {e}", file=sys.stderr)
                    self._upload_queue.put(item)

    def add_work(self, filename):
        self._upload_queue.put_nowait(filename)

    def stop_worker(self):
        self._upload_queue.put(None)

    def _upload(self, path: pathlib.Path):
        self._logger.debug(f"Uploading file ({path})")
        with open(path, "rb") as upload_file:
            self._check_ftp_connection()
            self._ftp.storbinary(f"STOR {path.name}", upload_file)
        self._logger.debug(f"Successfully uploaded file ({path})")

    def _start_ftps_connection(self):
        self._ftp = ftps = ftplib.FTP_TLS(host=self._ftps_dict["host"], user=self._ftps_dict["user"],
                                          passwd=self._ftps_dict["pw"])
        remote_path = self._ftps_dict["path"]
        try:
            ftps.mkd(remote_path)
        except ftplib.error_perm as e:
            if "550" in e.args[0]:
                pass
            else:
                raise e
        ftps.cwd(remote_path)
        self._logger.debug("Initialized FTPS connection")
        return ftps

    def _check_ftp_connection(self):
        try:
            self._ftp.voidcmd("NOOP")
        except (ftplib.error_temp, ftplib.error_perm) as e:
            if "421" in e.args[0]:
                self._ftp.close()
                self._ftp = self._start_ftps_connection()
            else:
                raise e

    def _delete_local_file(self, file):
        try:
            file.unlink()
        except FileNotFoundError:
            self._logger.error(f"Error deleting local file ({file})", exc_info=True)


if __name__ == '__main__':
    """
    Test your SFTP connection.
    """
    host = "fritz.box"
    user = "ftp_user"
    pw = "ftp_password"
    with ftplib.FTP_TLS(host=host, user=user, passwd=pw) as ftp:
        status = ftp.getwelcome()
        print(f'Connection status: {status}')
        ftp.cwd("test")
        with open("/home/pi/piLapse/img_5.png", "rb") as f:
            ftp.storbinary("STOR img_5.png", f)

        print(ftp.nlst())
