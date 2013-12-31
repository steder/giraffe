from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from collections import namedtuple
from io import BytesIO
import gzip
import os

from flask import Flask
from flask import request
from requests.exceptions import HTTPError
import tinys3
from wand.image import Image


"""
You'll need to set these environment variables:

 - AWS_ACCESS_KEY_ID
 - AWS_SECRET_ACCESS_KEY
 - GIRAFFE_BUCKET

I'd recommend setting them in your ``app.sh`` file.

"""

#
app = Flask(__name__)
app.debug = True


s3 = None
bucket = None


def connect_s3():
    global s3, bucket
    if not bucket:
        bucket = os.environ.get("GIRAFFE_BUCKET")
    if not s3:
        s3 = tinys3.Connection(os.environ.get("AWS_ACCESS_KEY_ID"),
                               os.environ.get("AWS_SECRET_ACCESS_KEY"),
                               default_bucket=bucket)
    return s3


ImageOp = namedtuple("ImageOp", 'function params')


@app.route("/")
def index():
    return "Hello World"


@app.route("/<path:path>")
def image_route(path):
    dirname = os.path.dirname(path)
    name = os.path.basename(path)
    try:
        base, ext = name.split(".")
    except:
        return "no extension specified", 404

    args = get_image_args(request.args)
    params = args.values()
    if params:
        return get_file_with_params_or_404(path, dirname, base, ext, args)
    else:
        return get_file_or_404(path)


def positive_int_or_none(value):
    try:
        value = int(value)
        if value >= 0:
            return value
        else:
            return None
    except ValueError:
        return None
    except TypeError:
        return None


def get_image_args(args):
    w = positive_int_or_none(args.get("w"))
    h = positive_int_or_none(args.get("h"))
    fit = args.get('fit')
    flip = args.get('flip')
    rot = positive_int_or_none(args.get("rot"))

    image_args = {}
    if w:
        image_args['w'] = w
    if h:
        image_args['h'] = h
    if fit:
        image_args['fit'] = fit
    if flip:
        image_args['flip'] = flip
    if rot:
        image_args['rot'] = rot

    return image_args


def get_object_or_none(path):
    try:
        obj = s3.get(path)
    except HTTPError as error:
        if error.response.status_code == 404:
            return None
        else:
            raise
    return obj


def get_file_or_404(path):
    key = get_object_or_none(path)
    if key:
        return key.content, 200, {"Content-Type": "image/jpeg"}
    else:
        return "404: file '{}' doesn't exist".format(path), 404


def process_image(img, operations):
    for op in operations:
        if callable(op.function):
            img = op.function(img, **op.params)
        if op.function == 'resize':
            img.resize(**op.params)
        if op.function == 'liquid':
            # this will raise a MissingDelegateError if you don't compile
            # imagemagick with the `--with-lqr` option.
            img.liquid_rescale(**op.params)
        if op.function == 'flip':
            img.flip()
        if op.function == 'flop':
            img.flop()
    return img


def fit_crop(img, width=None, height=None, anchor=None):
    # regarding offset: based on anchor being 'top', 'bottom', 'left', 'right'
    # we should adjust offset.  By default this empty offset
    # means we will always crop to the center.
    offset = '' 
    crop = "{}x{}{}".format(width, height, offset)
    resize = ''
    img.transform(crop, resize)
    return img


def build_pipeline(params):
    pipeline = []
    if 'h' in params and 'w' in params:
        fit = params.get('fit')

        if fit == 'crop':
            anchor = params.get('crop', 'center').lower()
            pipeline.append(
                ImageOp(fit_crop, {
                        'width': params['w'],
                        'height': params['h'],
                        'anchor': anchor,
                        }
                )
            )
        elif fit == 'liquid':
            pipeline.append(
                ImageOp('liquid', {'width': params['w'],
                                   'height': params['h']}
                        )
            )
        else:
            pipeline.append(
                ImageOp('resize', {'width': params['w'],
                                   'height': params['h']}
                        )
            )

    flip = params.get('flip')
    if flip:
        if 'h' in flip:
            pipeline.append(
                ImageOp('flop', {})
            )
        if 'v' in flip:
            pipeline.append(
                ImageOp('flip', {})
            )

    return pipeline


def image_to_buffer(img, format='JPEG', compress=False):
    buffer = BytesIO()
    img.format = format
    if compress:
        filename, mode, compresslevel, mtime = '', 'wb', 9, None
        gz = gzip.GzipFile(filename, mode, compresslevel, buffer, mtime)
        img.save(file=gz)
    else:
        img.save(file=buffer)
    return buffer


def image_to_binary(img, format='JPEG'):
    return img.make_blob(format)


def get_file_with_params_or_404(path, dirname, base, ext, args):
    print("we have params")
    key = get_object_or_none(path)
    if key:
        print("and the original path exists")
        stuff = [base,]
        stuff.extend(args.values())
        filename_with_args = "_".join(str(x) for x in stuff
                                   if x is not None) + "." + ext
        # if we enable compression we may want to modify the filename here to include *.gz
        key_name = os.path.join('cache', dirname, filename_with_args)
        custom_key = get_object_or_none(key_name)
        if custom_key:
            return custom_key.content, 200, {"Content-Type": "image/jpeg"}
        else:
            img = Image(blob=BytesIO(key.content))
            size = min(args.get('w', img.size[0]), img.size[0]), min(args.get('h', img.size[1]), img.size[1])
            if size != img.size:
                temp_handle = image_to_buffer(process_image(img, build_pipeline(args)), format='JPEG', compress=False)
                s3.upload(key_name, temp_handle, content_type="image/jpeg", rewind=True, public=True)
                temp_handle.seek(0)
                return temp_handle.read(), 200, {"Content-Type": "image/jpeg"}
            else:
                return key.content, 200, {"Content-Type": "image/jpeg"}
    else: 
        return "404: original file '{}' doesn't exist".format(path), 404


if __name__ == "__main__":
    connect_s3()
    app.run("0.0.0.0", 9876)
