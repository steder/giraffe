"""
"""

import unittest

import wand
from wand.color import Color
from wand.image import Image

import giraffe


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


class TestBuildPipelineFromParams(unittest.TestCase):
    def test_resize_only(self):
        pipeline = giraffe.build_pipeline(
           {"w": 100, "h": 50}
        )
        self.assertEqual(pipeline, 
            [giraffe.ImageOp('resize', {'width': 100, 'height': 50}),
            ]
        )


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


