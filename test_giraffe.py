"""
"""

from collections import OrderedDict
import unittest

import mock
import requests
from requests.exceptions import HTTPError
from wand.color import Color
from wand.drawing import Drawing
from wand.image import Image
from werkzeug.exceptions import BadRequest

import giraffe


class FlaskTestCase(unittest.TestCase):
    def setUp(self):
        giraffe.app.config['TESTING'] = True
        self.app = giraffe.app.test_client()

    def tearDown(self):
        pass


def make_httperror(code):
    response = mock.Mock()
    response.status_code = code
    e = requests.exceptions.HTTPError()
    e.response = response
    return e


class TestBuildPipelineFromParams(unittest.TestCase):
    def test_resize_only(self):
        pipeline = giraffe.build_pipeline(
           {"w": 100, "h": 50}
        )
        self.assertEqual(pipeline,
            [giraffe.ImageOp('resize', {'width': 100, 'height': 50}),
            ]
        )

    def test_resize_fit_crop_center(self):
        pipeline = giraffe.build_pipeline(
            {"w": 100, "h": 50,
             "fit": "crop",
             #"crop": None
             }
        )
        self.assertEqual(len(pipeline), 1)
        self.assertEqual(pipeline[0].function.__name__, "fit_crop")
        self.assertEqual(pipeline[0].params, {'anchor': 'center', 'height': 50, 'width': 100})

    def test_resize_fit_liquid(self):
        pipeline = giraffe.build_pipeline(
            {"w": 100, "h": 50,
             "fit": "liquid",
             #"crop": None
             }
        )
        self.assertEqual(len(pipeline), 1)
        self.assertEqual(pipeline[0].function, "liquid")
        self.assertEqual(pipeline[0].params, {'height': 50, 'width': 100})

    def test_format_png(self):
        pipeline = giraffe.build_pipeline(
            {"w": 100, "h": 50,
             "fm": "png",
             }
        )
        self.assertEqual(len(pipeline), 2)
        self.assertEqual(pipeline[0].function, "resize")
        self.assertEqual(pipeline[0].params, {'height': 50, 'width': 100})
        self.assertEqual(pipeline[1].function, "format")
        self.assertEqual(pipeline[1].params, {'format': 'png'})

    def test_rotate(self):
        pipeline = giraffe.build_pipeline(
            {"rot": 90}
        )

        self.assertEqual(pipeline,
            [giraffe.ImageOp('rotate', {'degrees' : 90}),
            ]
        )

    def test_bad_rotate(self):
        self.assertRaises(BadRequest, giraffe.build_pipeline, ({"rot":-1}))
        self.assertRaises(BadRequest, giraffe.build_pipeline, ({"rot":360}))
        self.assertRaises(BadRequest, giraffe.build_pipeline, ({"rot":"stringy"}))

        giraffe.build_pipeline({"rot":1.0})
        giraffe.build_pipeline({"rot":1.1})


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
        self.assertEqual(
            giraffe.get_image_args({}),
            {}
        )

    def test_negative_height(self):
        self.assertEqual(
            giraffe.get_image_args({'h': -100}),
            {}
        )

    def test_negative_width(self):
        self.assertEqual(
            giraffe.get_image_args({'w': -100}),
            {}
        )

    def test_valid_width(self):
        self.assertEqual(
            giraffe.get_image_args({'w': 100}),
            {'w': 100}
        )

    def test_valid_height(self):
        self.assertEqual(
            giraffe.get_image_args({'h': 100}),
            {'h': 100}
        )

    def test_valid_height_invalid_width(self):
        self.assertEqual(
            giraffe.get_image_args({'h': 100,
                                    'w': -100
                                }),
            {'h': 100}
        )

    def test_valid_height_and_width(self):
        self.assertEqual(
            giraffe.get_image_args({'h': 100,
                                    'w': 100
                                }),
            {'h': 100, 'w': 100}
        )

    def test_valid_height_and_width_extra_param_ignored(self):
        self.assertEqual(
            giraffe.get_image_args({'h': 100,
                                    'w': 100,
                                    'extra': 'hello world'
                                }),
            {'h': 100, 'w': 100}
        )

    def test_fit_crop(self):
        self.assertEqual(
            giraffe.get_image_args({'h': 100,
                                    'w': 100,
                                    'fit': 'crop',
                                    'crop': 'center'
                                }),
            {'h': 100, 'w': 100, 'fit': 'crop'}
        )

    def test_flip_vertical(self):
        self.assertEqual(giraffe.get_image_args({"flip": "v"}),
                         {'flip': 'v'})

    def test_flip_horizontal(self):
        self.assertEqual(giraffe.get_image_args({"flip": "h"}),
                         {'flip': 'h'})

    def test_flip_both(self):
        self.assertEqual(giraffe.get_image_args({"flip": "hv"}),
                         {'flip': 'hv'})

    def test_rotate(self):
        self.assertEqual(giraffe.get_image_args({"rot": 123}),
                         {"rot": 123})

    def test_fm_jpg(self):
        self.assertEqual(giraffe.get_image_args({"fm": "jpg"}),
                         {"fm": "jpg"})

    def test_fm_png(self):
        self.assertEqual(giraffe.get_image_args({"fm": "png"}),
                         {"fm": "png"})


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
        print("normal: %s, compressed: %s"%(uncompressed_size, compressed_size))
        self.assertLess(compressed_size, uncompressed_size)

    def test_image_to_binary(self):
        buffer = giraffe.image_to_buffer(self.image)
        self.assertEqual(buffer.getvalue(), giraffe.image_to_binary(self.image))


class TestImageResize(unittest.TestCase):
    def setUp(self):
        with Color('red') as bg:
            self.image = Image(width=1920, height=1080, background=bg)

    def test_resize(self):
        pipeline = [
            giraffe.ImageOp("resize", {'width':100, 'height': 100}),
        ]
        img = giraffe.process_image(self.image, pipeline)
        self.assertEqual(img.size, (100, 100))

    def test_fit_crop_center(self):
        pipeline = [giraffe.ImageOp(giraffe.fit_crop, {
                        'width': 100,
                        'height': 100,
                        'anchor': 'center',
                        }),
                    ]
        img = giraffe.process_image(self.image, pipeline)
        self.assertEqual(img.size, (100, 100))

    def test_fit_liquid(self):
        pipeline = [giraffe.ImageOp('liquid', {
                        'width': 100,
                        'height': 100,
                        }),
                    ]
        img = giraffe.process_image(self.image, pipeline)
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

        pipeline = [giraffe.ImageOp('rotate', {'degrees':90})]
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

class TestIndexRoute(FlaskTestCase):
    """
    Just a placeholder test:

    """
    def test_index(self):
        r = self.app.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, b"Hello World")


class TestImageRoute(FlaskTestCase):
    bucket = "wtf"

    def setUp(self):
        super(TestImageRoute, self).setUp()
        with Color('red') as bg:
            self.image = Image(width=1920, height=1080, background=bg)

        # let's clear the cache
        params = OrderedDict()
        params['w'] = 100
        params['h'] = 100
        giraffe.get_file_or_404.invalidate(self.bucket, "redbull.jpg")
        giraffe.get_file_with_params_or_404.invalidate(self.bucket, "redbull.jpg", "{}/redbull_w100_h100.jpg".format(giraffe.CACHE_DIR),
                                                       params)

    @mock.patch('giraffe.s3')
    def test_image_doesnt_exist(self, s3):
        s3.get.side_effect = make_httperror(404)
        r = self.app.get("/{}/redbull.jpg".format(self.bucket))
        self.assertEqual(r.status_code, 404)

    @mock.patch('giraffe.s3')
    def test_image_resize_original_doesnt_exist(self, s3):
        s3.get.side_effect = make_httperror(404)
        r = self.app.get("/{}/redbull.jpg?w=100&h=100".format(self.bucket))
        self.assertEqual(r.status_code, 404)

    def test_image_has_no_extension(self):
        r = self.app.get("/{}/foo".format(self.bucket))
        self.assertEqual(r.status_code, 404)

    def test_bucket_only(self):
        r = self.app.get("/{}".format(self.bucket))
        self.assertEqual(r.status_code, 404)

    # original image as jpeg:
    @mock.patch('giraffe.s3')
    def test_jpeg_exists(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("jpeg")
        obj.headers = {'content-type': 'image/jpeg'}
        s3.get.return_value = obj

        r = self.app.get("/{}/redbull.jpg".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        content_type = r.headers.get("content-type")
        self.assertEqual(content_type, "image/jpeg")
        self.assertEqual(Image(blob=r.data).format, 'JPEG')

    @mock.patch('giraffe.s3')
    def test_jpeg_exists_but_format_as_png(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("jpeg")
        obj.headers = {'content-type': 'image/jpeg'}

        s3.get.side_effect = [obj, make_httperror(404)]
        r = self.app.get("/{}/redbull.jpg?fm=png".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        content_type = r.headers.get("content-type")
        self.assertEqual(content_type, "image/png")
        args, kwargs = s3.upload.call_args
        self.assertEqual(args[0], "giraffe/redbull.png")
        self.assertEqual(kwargs['content_type'], "image/png")
        self.assertEqual(Image(blob=r.data).format, 'PNG')

    @mock.patch('giraffe.s3')
    def test_image_exists_but_needs_to_be_resized(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("jpeg")
        # we'll call s3.get twice, the first time we'll get the original file, the second time
        # we'll be calling to check for the specific version of the object.
        s3.get.side_effect = [obj, make_httperror(404)]
        r = self.app.get("/{}/redbull.jpg?w=100&h=100".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Image(blob=r.data).size, (100, 100))

    @mock.patch('giraffe.s3')
    def test_image_exists_but_user_wants_unnecessary_resize(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("jpeg")
        # we'll call s3.get twice, the first time we'll get the original file, the second time
        # we'll be calling to check for the specific version of the object.
        s3.get.side_effect = [obj, make_httperror(404)]
        r = self.app.get("/{}/redbull.jpg?w=1920&h=1080".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Image(blob=r.data).size, (1920, 1080))

    @mock.patch('giraffe.s3')
    def test_image_exists_and_has_already_been_resized(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("jpeg")
        obj2 = mock.Mock()
        with self.image.clone() as img:
            img.resize(100, 100)
            obj2.content = img.make_blob("jpeg")
        # we'll call s3.get twice, the first time we'll get the original file, the second time
        # we'll be calling to check for the specific version of the object.
        s3.get.side_effect = [obj, obj2]
        r = self.app.get("/{}/redbull.jpg?w=100&h=100".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Image(blob=r.data).size, (100, 100))

    # original image as png:
    @mock.patch('giraffe.s3')
    def test_png_exists(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("png")
        obj.headers = {'content-type': 'image/png'}
        s3.get.return_value = obj
        r = self.app.get("/{}/redbull.png".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        content_type = r.headers.get("content-type")
        self.assertEqual(content_type, "image/png")
        self.assertEqual(Image(blob=r.data).format, 'PNG')

    @mock.patch('giraffe.s3')
    def test_png_exists_but_needs_format_as_jpg(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("png")
        s3.get.side_effect = [obj, make_httperror(404)]
        r = self.app.get("/{}/redbull.png?fm=jpg".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        content_type = r.headers.get("content-type")
        self.assertEqual(content_type, "image/jpeg")
        args, kwargs = s3.upload.call_args
        self.assertEqual(args[0], "giraffe/redbull.jpg")
        self.assertEqual(kwargs['content_type'], "image/jpeg")
        self.assertEqual(Image(blob=r.data).format, 'JPEG')

    @mock.patch('giraffe.s3')
    def test_png_exists_but_needs_format_as_jpeg(self, s3):
        # yep, if someone uses "fm=jpeg" instead of "fm=jpg" it should still work
        obj = mock.Mock()
        obj.content = self.image.make_blob("png")
        s3.get.side_effect = [obj, make_httperror(404)]
        r = self.app.get("/{}/redbull.png?fm=jpeg".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        content_type = r.headers.get("content-type")
        self.assertEqual(content_type, "image/jpeg")
        self.assertEqual(Image(blob=r.data).format, 'JPEG')

    @mock.patch('giraffe.s3')
    def test_png_exists_but_needs_to_be_resized(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("png")
        # we'll call s3.get twice, the first time we'll get the original file, the second time
        # we'll be calling to check for the specific version of the object.
        s3.get.side_effect = [obj, make_httperror(404)]
        r = self.app.get("/{}/redbull.png?w=100&h=100".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Image(blob=r.data).size, (100, 100))

    @mock.patch('giraffe.s3')
    def test_png_exists_but_user_wants_unnecessary_resize(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("png")
        # we'll call s3.get twice, the first time we'll get the original file, the second time
        # we'll be calling to check for the specific version of the object.
        s3.get.side_effect = [obj, make_httperror(404)]
        r = self.app.get("/{}/redbull.png?w=1920&h=1080".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Image(blob=r.data).size, (1920, 1080))

    @mock.patch('giraffe.s3')
    def test_png_exists_and_has_already_been_resized(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("png")
        obj2 = mock.Mock()
        with self.image.clone() as img:
            img.resize(100, 100)
            obj2.content = img.make_blob("png")
        # we'll call s3.get twice, the first time we'll get the original file, the second time
        # we'll be calling to check for the specific version of the object.
        s3.get.side_effect = [obj, obj2]
        r = self.app.get("/{}/redbull.jpg?w=100&h=100".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Image(blob=r.data).size, (100, 100))

    # original image as bmp:
    @mock.patch('giraffe.s3')
    def test_bmp_exists(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("bmp")
        obj.headers = {'content-type': 'image/bmp'}
        s3.get.return_value = obj
        r = self.app.get("/{}/redbull.bmp".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        content_type = r.headers.get("content-type")
        self.assertEqual(content_type, "image/bmp")
        self.assertEqual(Image(blob=r.data).format, 'BMP')

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
        r = self.app.get("/{}/masquerading_gif.jpg?w=120&h=120".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        content_type = r.headers.get("content-type")
        self.assertEqual(content_type, "image/jpeg")
        self.assertEqual(Image(blob=r.data).format, 'JPEG')
        self.assertEqual(Image(blob=r.data).size, (120, 120))

    @mock.patch('giraffe.s3')
    def test_giant_image_resize(self, s3):
        obj = mock.Mock()
        self.image = Image(width=12402, height=8770)
        obj.content = self.image.make_blob("jpg")
        obj.headers = {'content-type': 'image/jpeg'}
        s3.get.side_effect = [obj, make_httperror(404)]
        r = self.app.get("/{}/giant.jpg?w=120&h=120".format(self.bucket))
        self.assertEqual(r.status_code, 200)
        content_type = r.headers.get("content-type")
        self.assertEqual(content_type, "image/jpeg")
        self.assertEqual(Image(blob=r.data).size, (120, 120))
