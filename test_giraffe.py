"""
"""

import unittest

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
