"""Run directly with python3 test/test_uploader_crop.py."""

from contextlib import closing
import importlib.util
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image
from werkzeug.datastructures import FileStorage


UPLOADER_PATH = Path(__file__).resolve().parents[1] / 'pybossa/uploader/__init__.py'
UPLOADER_SPEC = importlib.util.spec_from_file_location('uploader', UPLOADER_PATH)
UPLOADER_MODULE = importlib.util.module_from_spec(UPLOADER_SPEC)
UPLOADER_SPEC.loader.exec_module(UPLOADER_MODULE)
Uploader = UPLOADER_MODULE.Uploader


class TestUploaderCrop(unittest.TestCase):

    def make_upload(self, extension, image_format):
        stream = BytesIO()
        with Image.new('RGB', (100, 80), (10, 40, 90)) as source:
            source.paste((200, 60, 20), (20, 10, 70, 50))
            source.save(stream, format=image_format)
        stream.seek(0)
        return FileStorage(stream=stream, filename='image.' + extension)

    def test_crop_uploaded_images(self):
        for extension, image_format in (('png', 'PNG'), ('jpg', 'JPEG'),
                                        ('jpeg', 'JPEG'), ('gif', 'GIF')):
            with self.subTest(extension=extension):
                with closing(self.make_upload(extension, image_format)) as upload:
                    self.assertTrue(Uploader().crop(upload, (20, 10, 70, 50)))
                    self.assertEqual(upload.stream.tell(), 0)
                    with Image.open(upload.stream) as cropped:
                        cropped.load()
                        self.assertEqual(cropped.size, (50, 40))
                        self.assertEqual(cropped.format, image_format)
                        if image_format != 'JPEG':
                            self.assertEqual(cropped.convert('RGB').getpixel((0, 0)),
                                             (200, 60, 20))

    def test_zero_coordinates_preserve_image_size(self):
        for extension, image_format in (('png', 'PNG'), ('jpg', 'JPEG'),
                                        ('gif', 'GIF')):
            with self.subTest(extension=extension):
                with closing(self.make_upload(extension, image_format)) as upload:
                    self.assertTrue(Uploader().crop(upload, (0, 0, 0, 0)))
                    with Image.open(upload.stream) as output:
                        output.load()
                        self.assertEqual(output.size, (100, 80))
                        self.assertEqual(output.format, image_format)

    def test_invalid_image_returns_false(self):
        with closing(FileStorage(stream=BytesIO(b'not an image'),
                                 filename='image.png')) as upload:
            original_stream = upload.stream
            self.assertFalse(Uploader().crop(upload, (20, 10, 70, 50)))
            self.assertIs(upload.stream, original_stream)

    def test_upload_crops_before_saving(self):
        uploader = Uploader()
        with closing(self.make_upload('png', 'PNG')) as upload:
            with patch.object(uploader, '_upload_file', return_value='saved') as save:
                self.assertEqual(uploader.upload_file(upload, 'avatars',
                                                      coordinates=(20, 10, 70, 50)),
                                 'saved')
                save.assert_called_once_with(upload, 'avatars')
                with Image.open(upload.stream) as cropped:
                    cropped.load()
                    self.assertEqual(cropped.size, (50, 40))


if __name__ == '__main__':
    unittest.main()
