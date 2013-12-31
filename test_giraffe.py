"""
"""

import unittest

import mock
import requests
from wand.color import Color
from wand.image import Image

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


class TestGetObjectOrNone(unittest.TestCase):
    """
    This function is used to retrieve an object from S3
    or simply return None.

    """

    @mock.patch('giraffe.s3')
    def test_missing_object(self, s3):
        s3.get.side_effect = make_httperror(404)
        self.assertIsNone(giraffe.get_object_or_none("redbull.jpg"))

    @mock.patch('giraffe.s3')
    def test_existing_object(self, s3):
        s3.get.return_value = 'foo'
        self.assertEqual(giraffe.get_object_or_none("redbull.jpg"), 'foo')


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


class TestIndexRoute(FlaskTestCase):
    """
    Just a placeholder test:

    """
    def test_index(self):
        r = self.app.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, b"Hello World")


class TestImageRoute(FlaskTestCase):
    def setUp(self):
        super(TestImageRoute, self).setUp()
        with Color('red') as bg:
            self.image = Image(width=1920, height=1080, background=bg)

    @mock.patch('giraffe.s3')
    def test_image_doesnt_exist(self, s3):
        s3.get.side_effect = make_httperror(404)
        r = self.app.get("/redbull.jpg")
        self.assertEqual(r.status_code, 404)

    @mock.patch('giraffe.s3')
    def test_image_resize_original_doesnt_exist(self, s3):
        s3.get.side_effect = make_httperror(404)
        r = self.app.get("/redbull.jpg?w=100&h=100")
        self.assertEqual(r.status_code, 404)

    def test_image_has_no_extension(self):
        r = self.app.get("/foo")
        self.assertEqual(r.status_code, 404)

    @mock.patch('giraffe.s3')
    def test_image_exists(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("jpeg")
        s3.get.return_value = obj
        r = self.app.get("/redbull.jpg")
        self.assertEqual(r.status_code, 200)

    @mock.patch('giraffe.s3')
    def test_image_exists_but_needs_to_be_resized(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("jpeg")
        # we'll call s3.get twice, the first time we'll get the original file, the second time
        # we'll be calling to check for the specific version of the object.
        s3.get.side_effect = [obj, make_httperror(404)]
        r = self.app.get("/redbull.jpg?w=100&h=100")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Image(blob=r.data).size, (100, 100))

    @mock.patch('giraffe.s3')
    def test_image_exists_but_user_wants_unnecessary_resize(self, s3):
        obj = mock.Mock()
        obj.content = self.image.make_blob("jpeg")
        # we'll call s3.get twice, the first time we'll get the original file, the second time
        # we'll be calling to check for the specific version of the object.
        s3.get.side_effect = [obj, make_httperror(404)]
        r = self.app.get("/redbull.jpg?w=1920&h=1080")
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
        r = self.app.get("/redbull.jpg?w=100&h=100")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Image(blob=r.data).size, (100, 100))


