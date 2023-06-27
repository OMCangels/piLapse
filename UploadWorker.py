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
        self.__upload_queue = queue
        self.__delete_local = delete_local
        self.__termination_symbol = termination_symbol
        self.__ftp = None
        super().__init__(target=self.upload_files, args=(hostname, username, password, remote_path))

    def upload_files(self, hostname, username, password, remote_path):
        self.__start_remote_connection(hostname, username, password, remote_path)
        while True:
            file = self.__upload_queue.get()
            if file == self.__termination_symbol:
                return
            file = pathlib.Path(file)
            try:
                self._upload(file)
                if self.__delete_local:
                    try:
                        file.unlink()
                    except Exception as e:
                        print(f"Error deleting local file ({file}): {e}", file=sys.stderr)
            except Exception as e:
                print(f"Error uploading local file ({file}): {e}", file=sys.stderr)

    def start(self) -> None:
        self.set_worker(self)
        super().start()

    def add_work(self, filename):
        self.__upload_queue.put_nowait(filename)

    def stop_worker(self):
        self.__upload_queue.put(None)
        self.set_worker(None)

    def _upload(self, path: pathlib.Path):
        with open(path, "rb") as upload_file:
            self.__ftp.storbinary(f"STOR {path.name}", upload_file)

    #     TODO Log upload

    def __start_remote_connection(self, hostname, username, password, remote_path):
        self.__ftp = ftplib.FTP_TLS(host=hostname, user=username, passwd=password)
        try:
            self.__ftp.mkd(remote_path)
        except ftplib.error_perm as e:
            print(f"mkdir failed: {e}", file=sys.stderr)
        self.__ftp.cwd(remote_path)


if __name__ == '__main__':
    host = "fritz.box"
    user = "ftp_user"
    pw = "i_love_u"
    with ftplib.FTP_TLS(host=host, user=user, passwd=pw) as ftp:
        status = ftp.getwelcome()
        print(f'Connection status: {status}')
        ftp.cwd("test")
        with open("/home/pi/piLapse/img_5.png", "rb") as f:
            ftp.storbinary("STOR img_5.png", f)

        print(ftp.nlst())
