import datetime

import numpy as np
from PIL import Image


class MyCamera:
    def capture_continuous(self, output):
        counter = 0
        while True:
            filename = output.format(
                counter=counter,
                timestamp=datetime.datetime.now(),
            )
            color = np.random.choice(range(256), size=3)
            yield self._make_image(100, color, filename)
            counter += 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    @staticmethod
    def _make_image(size_in_px, color, path):
        ones = np.ones((size_in_px, size_in_px, 3))
        img_array = ones * color
        image = Image.fromarray(img_array.astype('uint8')).convert('RGB')
        image.save(path)
        return path
