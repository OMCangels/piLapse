class MyCamera:
    # TODO: create images on demand, with correct folder
    def capture_continuous(self, **kwargs):
        return self._images

    def __init__(self):
        self._images = [f"/home/pi/piLapse/img_{x}.png" for x in range(10)]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


if __name__ == '__main__':
    """
    Create images for testing.
    """
    import numpy
    from PIL import Image

    num_images = 10
    image_size_px = 250

    for num in range(num_images):
        imarray = numpy.random.rand(image_size_px, image_size_px, 3) * 255 * (num / num_images)
        im = Image.fromarray(imarray.astype('uint8')).convert('RGBA')
        im.save(f'/home/pi/piLapse/img_{num}.png')
