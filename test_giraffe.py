"""
Tests for FastAPI version of Giraffe
"""

from collections import OrderedDict
import os
import unittest

import mock
import pytest
import requests
from requests.exceptions import HTTPError
from fastapi.testclient import TestClient
from fastapi import HTTPException
from wand.color import Color
from wand.drawing import Drawing
from wand.exceptions import MissingDelegateError
from wand.image import Image
import giraffe


class FastAPITestCase(unittest.TestCase):
    def setUp(self):
        # Mock environment variables
        self.env_patcher = mock.patch.dict(os.environ, {
            'AWS_ACCESS_KEY_ID': 'mock_access_key',
            'AWS_SECRET_ACCESS_KEY': 'mock_secret_key',
            'ENV': 'testing',
            'GIRAFFE_SECRET': 'test_secret',
            'GIRAFFE_CACHE_DIR': 'test_cache'
        })
        self.env_patcher.start()
        
        # Create test client
        self.client = TestClient(giraffe.app)

    def tearDown(self):
        self.env_patcher.stop()


def make_httperror(code):
    response = mock.Mock()
    response.status_code = code
    e = requests.exceptions.HTTPError()
    e.response = response
    return e


class TestBuildPipelineFromParams(unittest.TestCase):
    def test_resize_only(self):
        pipeline = giraffe.build_pipeline({"w": 100, "h": 50})
        self.assertEqual(
            pipeline, [giraffe.ImageOp('resize', {'width': 100, 'height': 50})]
        )

    def test_resize_fit_crop_center(self):
        pipeline = giraffe.build_pipeline(
            {
                "w": 100,
                "h": 50,
                "fit": "crop",
                # "crop": None
            }
        )
        self.assertEqual(len(pipeline), 1)
        self.assertEqual(pipeline[0].function.__name__, "fit_crop")
        self.assertEqual(
            pipeline[0].params, {'anchor': 'center', 'height': 50, 'width': 100}
        )

    def test_resize_fit_liquid(self):
        pipeline = giraffe.build_pipeline(
            {
                "w": 100,
                "h": 50,
                "fit": "liquid",
                # "crop": None
            }
        )
        self.assertEqual(len(pipeline), 1)
        self.assertEqual(pipeline[0].function, "liquid")
        self.assertEqual(pipeline[0].params, {'height': 50, 'width': 100})

    def test_format_png(self):
        pipeline = giraffe.build_pipeline({"w": 100, "h": 50, "fm": "png"})
        self.assertEqual(len(pipeline), 2)
        self.assertEqual(pipeline[0].function, "resize")
        self.assertEqual(pipeline[0].params, {'height': 50, 'width': 100})
        self.assertEqual(pipeline[1].function, "format")
        self.assertEqual(pipeline[1].params, {'format': 'png'})

    def test_rotate(self):
        pipeline = giraffe.build_pipeline({"rot": 90})

        self.assertEqual(pipeline, [giraffe.ImageOp('rotate', {'degrees': 90})])

    def test_bad_rotate(self):
        self.assertRaises(HTTPException, giraffe.build_pipeline, ({"rot": -1}))
        self.assertRaises(HTTPException, giraffe.build_pipeline, ({"rot": 360}))
        self.assertRaises(HTTPException, giraffe.build_pipeline, ({"rot": "stringy"}))

        giraffe.build_pipeline({"rot": 1.0})
        giraffe.build_pipeline({"rot": 1.1})


class TestExtractingFormats(unittest.TestCase):
    def test_dot_jpg(self):
        self.assertEqual(giraffe.extension_to_format(".jpg"), "jpg")

    def test_jpg(self):
        self.assertEqual(giraffe.extension_to_format("jpg"), "jpg")

    def test_JPG(self):
        self.assertEqual(giraffe.extension_to_format("JPG"), "jpg")

    def test_jpe(self):
        self.assertEqual(giraffe.extension_to_format("JPE"), "jpg")

    def test_jpeg(self):
        self.assertEqual(giraffe.extension_to_format("JpEg"), "jpg")

    def test_gif(self):
        self.assertEqual(giraffe.extension_to_format("gif"), "gif")

    def test_GIF(self):
        self.assertEqual(giraffe.extension_to_format("GIF"), "gif")

    def test_dot_gif(self):
        self.assertEqual(giraffe.extension_to_format(".GIF"), "gif")

    def test_filename_jpg(self):
        self.assertEqual(giraffe.path_to_format("hello.jpeg"), "jpg")

    def test_filename_gif(self):
        self.assertEqual(giraffe.path_to_format("hello.gif"), "gif")

    def test_path_jpg(self):
        self.assertEqual(giraffe.path_to_format("foo/bar/baz/hello.jpg"), "jpg")


class TestGetImageArgs(unittest.TestCase):
    def test_no_params(self):
        self.assertEqual(giraffe.get_image_args({}), {})

    def test_negative_height(self):
        self.assertEqual(giraffe.get_image_args({'h': -100}), {})

    def test_negative_width(self):
        self.assertEqual(giraffe.get_image_args({'w': -100}), {})

    def test_valid_width(self):
        self.assertEqual(giraffe.get_image_args({'w': 100}), {'w': 100})

    def test_valid_height(self):
        self.assertEqual(giraffe.get_image_args({'h': 100}), {'h': 100})

    def test_valid_height_invalid_width(self):
        self.assertEqual(giraffe.get_image_args({'h': 100, 'w': -100}), {'h': 100})

    def test_valid_height_and_width(self):
        self.assertEqual(
            giraffe.get_image_args({'h': 100, 'w': 100}), {'h': 100, 'w': 100}
        )

    def test_valid_height_and_width_extra_param_ignored(self):
        self.assertEqual(
            giraffe.get_image_args({'h': 100, 'w': 100, 'extra': 'hello world'}),
            {'h': 100, 'w': 100},
        )

    def test_fit_crop(self):
        self.assertEqual(
            giraffe.get_image_args(
                {'h': 100, 'w': 100, 'fit': 'crop', 'crop': 'center'}
            ),
            {'h': 100, 'w': 100, 'fit': 'crop'},
        )

    def test_flip_vertical(self):
        self.assertEqual(giraffe.get_image_args({"flip": "v"}), {'flip': 'v'})

    def test_flip_horizontal(self):
        self.assertEqual(giraffe.get_image_args({"flip": "h"}), {'flip': 'h'})

    def test_flip_both(self):
        self.assertEqual(giraffe.get_image_args({"flip": "hv"}), {'flip': 'hv'})

    def test_rotate(self):
        self.assertEqual(giraffe.get_image_args({"rot": 123}), {"rot": 123})

    def test_fm_jpg(self):
        self.assertEqual(giraffe.get_image_args({"fm": "jpg"}), {"fm": "jpg"})

    def test_fm_png(self):
        self.assertEqual(giraffe.get_image_args({"fm": "png"}), {"fm": "png"})


class TestGetObjectOrNone(unittest.TestCase):
    """
    This function is used to retrieve an object from S3
    or simply return None.

    """

    bucket = "test.giraffe.bucket"

    @mock.patch('giraffe.s3')
    def test_missing_object(self, s3):
        s3.get.side_effect = make_httperror(404)
        self.assertIsNone(giraffe.get_object_or_none(self.bucket, "redbull.jpg"))

    @mock.patch('giraffe.s3')
    def test_existing_object(self, s3):
        s3.get.return_value = 'foo'
        self.assertEqual(giraffe.get_object_or_none(self.bucket, "redbull.jpg"), 'foo')


class TestGetFileOr404(unittest.TestCase):
    pass


class TestImageToBuffer(unittest.TestCase):
    def setUp(self):
        with Color('red') as bg:
            self.image = Image(width=1920, height=1080, background=bg)

    def test_buffer(self):
        buffer = giraffe.image_to_buffer(self.image)
        # a valid jpeg buffer should have JFIF in the first few bytes
        self.assertIn(b"JFIF", buffer.getvalue()[:100])

    def test_compressed_buffer(self):
        # because this is just a simple red background it compresses VERY well
        # from 12528 to 206 bytes.
        #
        # Of course, for real images it may not be worth compressing them at all.
        buffer = giraffe.image_to_buffer(self.image)
        compressed_buffer = giraffe.image_to_buffer(self.image, compress=True)
        compressed_size = len(compressed_buffer.getvalue())
        uncompressed_size = len(buffer.getvalue())
        print("normal: %s, compressed: %s" % (uncompressed_size, compressed_size))
        self.assertLess(compressed_size, uncompressed_size)

    def test_image_to_binary(self):
        buffer = giraffe.image_to_buffer(self.image)
        self.assertEqual(buffer.getvalue(), giraffe.image_to_binary(self.image))


class TestImageResize(unittest.TestCase):
    def setUp(self):
        with Color('red') as bg:
            self.image = Image(width=1920, height=1080, background=bg)

    def test_resize(self):
        pipeline = [giraffe.ImageOp("resize", {'width': 100, 'height': 100})]
        img = giraffe.process_image(self.image, pipeline)
        self.assertEqual(img.size, (100, 100))

    def test_fit_crop_center(self):
        pipeline = [
            giraffe.ImageOp(
                giraffe.fit_crop, {'width': 100, 'height': 100, 'anchor': 'center'}
            )
        ]
        img = giraffe.process_image(self.image, pipeline)
        self.assertEqual(img.size, (100, 100))

    def test_fit_liquid(self):
        pipeline = [giraffe.ImageOp('liquid', {'width': 100, 'height': 100})]
        try:
            img = giraffe.process_image(self.image, pipeline)
        except MissingDelegateError:
            pytest.skip("ImageMagick doesn't have Liquid Rescale support compiled in")
        self.assertEqual(img.size, (100, 100))


class TestImageRotate(unittest.TestCase):
    def test_rotate(self):
        # draw an image with a single red column in the middle
        with Color('white') as bg, Color('red') as fg:
            image = Image(width=100, height=100, background=bg)
            with Drawing() as draw:
                draw.fill_color = fg
                draw.stroke_color = fg
                draw.rectangle(left=50, top=0, right=54, bottom=image.height)
                draw(image)

        pipeline = [giraffe.ImageOp('rotate', {'degrees': 90})]
        rotated_image = giraffe.process_image(image, pipeline)

        # verify that that image has a sideways bar of red in the middle
        for i, row in enumerate(rotated_image):
            for col in row:
                self.assertEqual(col.red, 1.0)

                if 50 <= i <= 54:
                    self.assertEqual(col.blue, 0.0)
                    self.assertEqual(col.green, 0.0)
                else:
                    self.assertNotEqual(col.blue, 0.0)
                    self.assertNotEqual(col.green, 0.0)


class TestIndexRoute(FastAPITestCase):
    """
    Just a placeholder test:

    """

    def test_index(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)


class TestImageRoute(FastAPITestCase):
    bucket = "wtf"

    def setUp(self):
        super(TestImageRoute, self).setUp()
        with Color('red') as bg:
            self.image = Image(width=1920, height=1080, background=bg)

    @mock.patch('giraffe.s3')
    def test_image_doesnt_exist(self, s3):
        s3.get.side_effect = make_httperror(404)
        r = self.client.get("/{}/redbull.jpg".format(self.bucket))
        self.assertEqual(r.status_code, 404)

    @mock.patch('giraffe.s3')
    def test_image_resize_original_doesnt_exist(self, s3):
        s3.get.side_effect = make_httperror(404)
        r = self.client.get("/{}/redbull.jpg?w=100&h=100".format(self.bucket))
        self.assertEqual(r.status_code, 404)

    def test_image_has_no_extension(self):
        r = self.client.get("/{}/foo".format(self.bucket))
        self.assertEqual(r.status_code, 404)

    def test_bucket_only(self):
        r = self.client.get("/{}".format(self.bucket))
        self.assertEqual(r.status_code, 404)

    # original image as jpeg:
    @mock.patch('giraffe.s3')
    def test_jpeg_exists(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("jpeg")
        obj.headers = {'content-type': 'image/jpeg'}
        s3.get.return_value = obj

        r = self.client.get("/{}/redbull.jpg".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        content_type = r.headers.get("content-type")
        self.assertEqual(content_type, "image/jpeg")
        self.assertEqual(Image(blob=r.content).format, 'JPEG')

    @mock.patch('giraffe.s3')
    def test_jpeg_exists_but_format_as_png(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("jpeg")
        obj.headers = {'content-type': 'image/jpeg'}

        s3.get.side_effect = [obj, make_httperror(404)]
        r = self.client.get("/{}/redbull.jpg?fm=png".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        content_type = r.headers.get("content-type")
        self.assertEqual(content_type, "image/png")
        args, kwargs = s3.upload.call_args
        self.assertEqual(args[0], "giraffe/redbull.png")
        self.assertEqual(kwargs['content_type'], "image/png")
        self.assertEqual(Image(blob=r.content).format, 'PNG')

    @mock.patch('giraffe.s3')
    def test_image_exists_but_needs_to_be_resized(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("jpeg")
        # we'll call s3.get twice, the first time we'll get the original file, the second time
        # we'll be calling to check for the specific version of the object.
        s3.get.side_effect = [obj, make_httperror(404)]
        r = self.client.get("/{}/redbull.jpg?w=100&h=100".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Image(blob=r.content).size, (100, 100))

    @mock.patch('giraffe.s3')
    def test_image_exists_but_user_wants_unnecessary_resize(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("jpeg")
        # we'll call s3.get twice, the first time we'll get the original file, the second time
        # we'll be calling to check for the specific version of the object.
        s3.get.side_effect = [obj, make_httperror(404)]
        r = self.client.get("/{}/redbull.jpg?w=1920&h=1080".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Image(blob=r.content).size, (1920, 1080))

    @mock.patch('giraffe.s3')
    def test_image_exists_and_has_already_been_resized(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("jpeg")
        obj.headers = {'content-type': 'image/jpeg'}
        obj2 = mock.Mock()
        with self.image.clone() as img:
            img.resize(100, 100)
            obj2.content = img.make_blob("jpeg")
        obj2.headers = {'content-type': 'image/jpeg'}
        # we'll call s3.get twice, the first time we'll get the original file, the second time
        # we'll be calling to check for the specific version of the object.
        s3.get.side_effect = [obj, obj2]
        r = self.client.get("/{}/redbull.jpg?w=100&h=100".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Image(blob=r.content).size, (100, 100))

    # original image as png:
    @mock.patch('giraffe.s3')
    def test_png_exists(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("png")
        obj.headers = {'content-type': 'image/png'}
        s3.get.return_value = obj
        r = self.client.get("/{}/redbull.png".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        content_type = r.headers.get("content-type")
        self.assertEqual(content_type, "image/png")
        self.assertEqual(Image(blob=r.content).format, 'PNG')

    @mock.patch('giraffe.s3')
    def test_png_exists_but_needs_format_as_jpg(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("png")
        s3.get.side_effect = [obj, make_httperror(404)]
        r = self.client.get("/{}/redbull.png?fm=jpg".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        content_type = r.headers.get("content-type")
        self.assertEqual(content_type, "image/jpeg")
        args, kwargs = s3.upload.call_args
        self.assertEqual(args[0], "giraffe/redbull.jpg")
        self.assertEqual(kwargs['content_type'], "image/jpeg")
        self.assertEqual(Image(blob=r.content).format, 'JPEG')

    @mock.patch('giraffe.s3')
    def test_png_exists_but_needs_format_as_jpeg(self, s3):
        # yep, if someone uses "fm=jpeg" instead of "fm=jpg" it should still work
        obj = mock.Mock()
        obj.content = self.image.make_blob("png")
        s3.get.side_effect = [obj, make_httperror(404)]
        r = self.client.get("/{}/redbull.png?fm=jpeg".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        content_type = r.headers.get("content-type")
        self.assertEqual(content_type, "image/jpeg")
        self.assertEqual(Image(blob=r.content).format, 'JPEG')

    @mock.patch('giraffe.s3')
    def test_png_exists_but_needs_to_be_resized(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("png")
        # we'll call s3.get twice, the first time we'll get the original file, the second time
        # we'll be calling to check for the specific version of the object.
        s3.get.side_effect = [obj, make_httperror(404)]
        r = self.client.get("/{}/redbull.png?w=100&h=100".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Image(blob=r.content).size, (100, 100))

    @mock.patch('giraffe.s3')
    def test_png_exists_but_user_wants_unnecessary_resize(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("png")
        # we'll call s3.get twice, the first time we'll get the original file, the second time
        # we'll be calling to check for the specific version of the object.
        s3.get.side_effect = [obj, make_httperror(404)]
        r = self.client.get("/{}/redbull.png?w=1920&h=1080".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Image(blob=r.content).size, (1920, 1080))

    @mock.patch('giraffe.s3')
    def test_png_exists_and_has_already_been_resized(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("png")
        obj.headers = {'content-type': 'image/png'}
        obj2 = mock.Mock()
        with self.image.clone() as img:
            img.resize(100, 100)
            obj2.content = img.make_blob("png")
        obj2.headers = {'content-type': 'image/png'}
        # we'll call s3.get twice, the first time we'll get the original file, the second time
        # we'll be calling to check for the specific version of the object.
        s3.get.side_effect = [obj, obj2]
        r = self.client.get("/{}/redbull.jpg?w=100&h=100".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Image(blob=r.content).size, (100, 100))

    # original image as bmp:
    @mock.patch('giraffe.s3')
    def test_bmp_exists(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("bmp")
        obj.headers = {'content-type': 'image/bmp'}
        s3.get.return_value = obj
        r = self.client.get("/{}/redbull.bmp".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        content_type = r.headers.get("content-type")
        self.assertEqual(content_type, "image/bmp")
        self.assertEqual(Image(blob=r.content).format, 'BMP')

    @mock.patch('giraffe.s3')
    def test_masquerading_gif_converted_to_jpeg(self, s3):
        """
        Assuming that a user uploads a gif file but it is named "foo.jpg"
        that gif can be resized but it won't resize correctly if we don't
        convert the format of the file from gif to jpg.

        """
        obj = mock.Mock()
        self.image = Image(width=160, height=120)
        obj.content = self.image.make_blob("gif")
        obj.headers = {'content-type': 'image/jpeg'}
        s3.get.side_effect = [obj, make_httperror(404)]
        r = self.client.get("/{}/masquerading_gif.jpg?w=120&h=120".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        content_type = r.headers.get("content-type")
        self.assertEqual(content_type, "image/jpeg")
        self.assertEqual(Image(blob=r.content).format, 'JPEG')
        self.assertEqual(Image(blob=r.content).size, (120, 120))

    @mock.patch('giraffe.s3')
    def test_giant_image_resize(self, s3):
        obj = mock.Mock()
        self.image = Image(width=12402, height=8770)
        obj.content = self.image.make_blob("jpg")
        obj.headers = {'content-type': 'image/jpeg'}
        s3.get.side_effect = [obj, make_httperror(404)]
        r = self.client.get("/{}/giant.jpg?w=120&h=120".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        content_type = r.headers.get("content-type")
        self.assertEqual(content_type, "image/jpeg")
        self.assertEqual(Image(blob=r.content).size, (120, 120))

    @mock.patch('giraffe.s3')
    def test_ico_masquerading_as_jpg(self, s3):
        obj = mock.Mock()
        image = Image(width=16, height=16)
        obj.content = image.make_blob('ico')
        obj.headers = {'content-type': 'image/jpeg'}  # this is what S3 tells us =(
        s3.get.side_effect = [obj, make_httperror(404)]
        r = self.client.get("/{}/giant.jpg?w=64&h=64".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        content_type = r.headers.get("content-type")
        self.assertEqual(content_type, "image/jpeg")
        self.assertEqual(Image(blob=r.content, format='jpeg').size, (64, 64))

    @mock.patch('giraffe.s3')
    def test_ico_masquerading_as_jpg_big(self, s3):
        obj = mock.Mock()
        image = Image(width=16, height=16)
        obj.content = image.make_blob('ico')
        obj.headers = {'content-type': 'image/jpeg'}  # this is what S3 tells us =(
        s3.get.side_effect = [obj, make_httperror(404)]
        r = self.client.get("/{}/giant.jpg?w=400&h=400".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        content_type = r.headers.get("content-type")
        self.assertEqual(content_type, "image/jpeg")
        self.assertEqual(Image(blob=r.content, format='jpeg').size, (400, 400))


class TestOverlayRoutes(FastAPITestCase):
    bucket = "wtf"

    def setUp(self):
        super(TestOverlayRoutes, self).setUp()
        with Color('red') as bg:
            self.image = Image(width=1920, height=1080, background=bg)

    @mock.patch('giraffe.s3')
    def test_image_overlay_relative_url(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("png")
        # s3 requests for 1. original image, 2. generated image with overlay, 3. overlay
        s3.get.side_effect = [obj, make_httperror(404), obj]
        r = self.client.get(
            "/{b}/art.png?overlay=/{b}/tshirts/overlay.png&bg=451D74".format(
                b=self.bucket
            )
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Image(blob=r.content).size, (1920, 1080))

    @mock.patch('giraffe.s3')
    def test_image_overlay_no_bg_color(self, s3):
        # background isn't required, if your original image doesn't include transparency
        # then you don't need the background color
        obj = mock.Mock()
        obj.content = self.image.make_blob("jpg")
        # s3 requests for 1. original image, 2. generated image with overlay, 3. overlay
        s3.get.side_effect = [obj, make_httperror(404), obj]
        r = self.client.get(
            "/{b}/art.jpg?overlay=/{b}/tshirts/overlay.png".format(b=self.bucket)
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Image(blob=r.content).size, (1920, 1080))

    @mock.patch('giraffe.requests')
    @mock.patch('giraffe.s3')
    def test_image_overlay_absolute_url(self, s3, requests):
        obj = mock.Mock()
        obj.content = self.image.make_blob("png")
        s3.get.side_effect = [obj, make_httperror(404)]
        requests.get.side_effect = [obj]

        r = self.client.get(
            "/{}/art.png?overlay=https://cloudfront.whatever.org/tshirts/overlay.png&bg=451D74".format(
                self.bucket
            )
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Image(blob=r.content).size, (1920, 1080))

    @mock.patch('giraffe.s3')
    def test_image_overlay_resize(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("png")
        s3.get.side_effect = [obj, make_httperror(404), obj]
        r = self.client.get(
            "/{b}/art.png?overlay=/{b}/tshirts/overlay.png&bg=451D74&w=100&h=100".format(
                b=self.bucket
            )
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Image(blob=r.content).size, (100, 100))


class TestSanitizeExtension(unittest.TestCase):
    """Test cases for the sanitize_extension function"""

    def test_valid_extension(self):
        """Test valid alphanumeric extensions"""
        self.assertEqual(giraffe.sanitize_extension("jpg"), "jpg")
        self.assertEqual(giraffe.sanitize_extension("png"), "png")
        self.assertEqual(giraffe.sanitize_extension("gif"), "gif")
        self.assertEqual(giraffe.sanitize_extension("webp"), "webp")

    def test_extension_with_leading_dot(self):
        """Test extensions with leading dots are stripped"""
        self.assertEqual(giraffe.sanitize_extension(".jpg"), "jpg")
        self.assertEqual(giraffe.sanitize_extension(".png"), "png")
        self.assertEqual(giraffe.sanitize_extension(".gif"), "gif")

    def test_uppercase_extension(self):
        """Test uppercase extensions are converted to lowercase"""
        self.assertEqual(giraffe.sanitize_extension("JPG"), "jpg")
        self.assertEqual(giraffe.sanitize_extension("PNG"), "png")
        self.assertEqual(giraffe.sanitize_extension("GIF"), "gif")
        self.assertEqual(giraffe.sanitize_extension(".JPEG"), "jpeg")

    def test_mixed_case_extension(self):
        """Test mixed case extensions are converted to lowercase"""
        self.assertEqual(giraffe.sanitize_extension("JpG"), "jpg")
        self.assertEqual(giraffe.sanitize_extension("PnG"), "png")
        self.assertEqual(giraffe.sanitize_extension("GiF"), "gif")

    def test_empty_extension(self):
        """Test empty/None extensions return empty string"""
        self.assertEqual(giraffe.sanitize_extension(""), "")
        self.assertEqual(giraffe.sanitize_extension(None), "")

    def test_extension_with_special_characters(self):
        """Test extensions with special characters are rejected"""
        self.assertEqual(giraffe.sanitize_extension("jpg!"), "")
        self.assertEqual(giraffe.sanitize_extension("png@"), "")
        self.assertEqual(giraffe.sanitize_extension("gif#"), "")
        self.assertEqual(giraffe.sanitize_extension("jpg-old"), "")
        self.assertEqual(giraffe.sanitize_extension("png_new"), "")
        self.assertEqual(giraffe.sanitize_extension("gif.bak"), "")

    def test_extension_with_spaces(self):
        """Test extensions with spaces are rejected"""
        self.assertEqual(giraffe.sanitize_extension("jpg "), "")
        self.assertEqual(giraffe.sanitize_extension(" png"), "")
        self.assertEqual(giraffe.sanitize_extension("gi f"), "")

    def test_extension_too_long(self):
        """Test extensions longer than MAX_EXTENSION_LENGTH are rejected"""
        # MAX_EXTENSION_LENGTH is 10, so 11 characters should be rejected
        long_extension = "a" * (giraffe.MAX_EXTENSION_LENGTH + 1)
        self.assertEqual(giraffe.sanitize_extension(long_extension), "")
        
        # Exactly MAX_EXTENSION_LENGTH should be accepted
        max_length_extension = "a" * giraffe.MAX_EXTENSION_LENGTH
        self.assertEqual(giraffe.sanitize_extension(max_length_extension), max_length_extension)

    def test_extension_with_numbers(self):
        """Test extensions with numbers are allowed"""
        self.assertEqual(giraffe.sanitize_extension("jpg2"), "jpg2")
        self.assertEqual(giraffe.sanitize_extension("png32"), "png32")
        self.assertEqual(giraffe.sanitize_extension("gif89a"), "gif89a")

    def test_numeric_extension(self):
        """Test purely numeric extensions are allowed"""
        self.assertEqual(giraffe.sanitize_extension("123"), "123")
        self.assertEqual(giraffe.sanitize_extension("456"), "456")

    def test_extension_with_dots_stripped(self):
        """Test multiple dots are handled correctly"""
        self.assertEqual(giraffe.sanitize_extension("...jpg"), "jpg")
        self.assertEqual(giraffe.sanitize_extension(".....png"), "png")

    def test_just_dots(self):
        """Test input with only dots"""
        self.assertEqual(giraffe.sanitize_extension("."), "")
        self.assertEqual(giraffe.sanitize_extension("..."), "")

    def test_whitespace_stripping(self):
        """Test whitespace around dots is handled"""
        self.assertEqual(giraffe.sanitize_extension(" .jpg "), "")  # Space makes it invalid
        self.assertEqual(giraffe.sanitize_extension(".jpg "), "")   # Trailing space makes it invalid


class TestExtensionToFormatWithSanitization(unittest.TestCase):
    """Test cases for extension_to_format with the new sanitization"""

    def test_valid_jpeg_extensions(self):
        """Test valid JPEG extensions are handled correctly"""
        self.assertEqual(giraffe.extension_to_format("jpg"), "jpg")
        self.assertEqual(giraffe.extension_to_format("jpeg"), "jpg")
        self.assertEqual(giraffe.extension_to_format("jpe"), "jpg")
        self.assertEqual(giraffe.extension_to_format("JPG"), "jpg")
        self.assertEqual(giraffe.extension_to_format("JPEG"), "jpg")

    def test_invalid_extension_raises_error(self):
        """Test that invalid extensions raise ValueError"""
        with self.assertRaises(ValueError):
            giraffe.extension_to_format("jpg!")
        with self.assertRaises(ValueError):
            giraffe.extension_to_format("png@#$")
        with self.assertRaises(ValueError):
            giraffe.extension_to_format("a" * 20)  # Too long

    def test_empty_extension_raises_error(self):
        """Test that empty extensions raise ValueError"""
        with self.assertRaises(ValueError):
            giraffe.extension_to_format("")
        with self.assertRaises(ValueError):
            giraffe.extension_to_format(None)

    def test_valid_non_jpeg_extensions(self):
        """Test valid non-JPEG extensions work correctly"""
        self.assertEqual(giraffe.extension_to_format("png"), "png")
        self.assertEqual(giraffe.extension_to_format("gif"), "gif")
        self.assertEqual(giraffe.extension_to_format("webp"), "webp")


class TestNormalizeMimetypeWithSanitization(unittest.TestCase):
    """Test cases for normalize_mimetype with the new sanitization"""

    def test_valid_jpeg_extensions(self):
        """Test valid JPEG extensions return 'jpeg'"""
        self.assertEqual(giraffe.normalize_mimetype("jpg"), "jpeg")
        self.assertEqual(giraffe.normalize_mimetype("jpeg"), "jpeg")
        self.assertEqual(giraffe.normalize_mimetype("jpe"), "jpeg")
        self.assertEqual(giraffe.normalize_mimetype("JPG"), "jpeg")
        self.assertEqual(giraffe.normalize_mimetype("JPEG"), "jpeg")

    def test_invalid_extension_raises_error(self):
        """Test that invalid extensions raise ValueError"""
        with self.assertRaises(ValueError):
            giraffe.normalize_mimetype("jpg!")
        with self.assertRaises(ValueError):
            giraffe.normalize_mimetype("png@#$")
        with self.assertRaises(ValueError):
            giraffe.normalize_mimetype("a" * 20)  # Too long

    def test_empty_extension_raises_error(self):
        """Test that empty extensions raise ValueError"""
        with self.assertRaises(ValueError):
            giraffe.normalize_mimetype("")
        with self.assertRaises(ValueError):
            giraffe.normalize_mimetype(None)

    def test_valid_non_jpeg_extensions(self):
        """Test valid non-JPEG extensions return the sanitized extension"""
        self.assertEqual(giraffe.normalize_mimetype("png"), "png")
        self.assertEqual(giraffe.normalize_mimetype("gif"), "gif")
        self.assertEqual(giraffe.normalize_mimetype("webp"), "webp")
        self.assertEqual(giraffe.normalize_mimetype("PNG"), "png")
        self.assertEqual(giraffe.normalize_mimetype("GIF"), "gif")
