import ftplib
import pathlib
import sys
from multiprocessing import Process, Queue
from typing import Optional


class UploadWorker(Process):
    __active_worker: Optional['UploadWorker'] = None

    @classmethod
    def get_worker(cls):
        return UploadWorker.__active_worker

    @classmethod
    def set_worker(cls, worker):
        UploadWorker.__active_worker = worker

    def __init__(self, hostname, remote_path, username, password, queue: Queue, delete_local, termination_symbol=None):
        self._upload_queue = queue
        self._delete_local = delete_local
        self._termination_symbol = termination_symbol
        self._ftp = None
        super().__init__(target=self.upload_files, args=(hostname, username, password, remote_path))

    def upload_files(self, hostname, username, password, remote_path):
        self._start_remote_connection(hostname, username, password, remote_path)
        while True:
            item = self._upload_queue.get()
            if item == self._termination_symbol:
                return
            file = pathlib.Path(item)
            try:
                self._upload(file)
                if self._delete_local:
                    self._delete_local_file(file)
            except Exception as e:
                print(f"Error uploading local file ({file}): {e}", file=sys.stderr)

    @staticmethod
    def _delete_local_file(file):
        try:
            file.unlink()
        except Exception as e:
            print(f"Error deleting local file ({file}): {e}", file=sys.stderr)

    def start(self) -> None:
        self.set_worker(self)
        super().start()

    def add_work(self, filename):
        self._upload_queue.put_nowait(filename)

    def stop_worker(self):
        self._upload_queue.put(None)
        self.set_worker(None)

    def _upload(self, path: pathlib.Path):
        #     TODO Log upload
        with open(path, "rb") as upload_file:
            self._ftp.storbinary(f"STOR {path.name}", upload_file)

    def _start_remote_connection(self, hostname, username, password, remote_path):
        self._ftp = ftplib.FTP_TLS(host=hostname, user=username, passwd=password)
        self._ftp.mkd(remote_path)
        self._ftp.cwd(remote_path)


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
