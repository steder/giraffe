from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from collections import namedtuple
from collections import OrderedDict
from io import BytesIO
import gzip
import os

from dogpile.cache import make_region
from dogpile.cache.util import sha1_mangle_key
from flask import Flask
from flask import request
from requests.exceptions import HTTPError
import tinys3
from wand.image import Image


"""
You'll need to set these environment variables:

 - AWS_ACCESS_KEY_ID
 - AWS_SECRET_ACCESS_KEY

I'd recommend setting them in your ``app.sh`` file.

"""

#
app = Flask(__name__)
ENV = os.environ.get("ENV", "development").lower()
if ENV == "production":
    app.debug = False
elif ENV == "staging":
    app.debug = False
else:
    app.debug = True
CACHE_URLS = os.environ.get("MEMCACHED").split(";") if os.environ.get("MEMCACHED") else []

s3 = None
CACHE_DIR = 'giraffe'
CACHE_CONTROL = "max-age=2592000"
DEFAULT_QUALITY = 75


if CACHE_URLS:
    print("starting up with memcached: %s"%(CACHE_URLS,))
    region = make_region(key_mangler=sha1_mangle_key).configure(
        'dogpile.cache.bmemcached',
        expiration_time=86400,
        arguments = {
            'url': CACHE_URLS,
            'distributed_lock': True,
        },
    )
else:
    print("starting up with in-process memory cache")
    region = make_region().configure(
        'dogpile.cache.memory',
        expiration_time=300,
    )


def connect_s3():
    global s3
    if not s3:
        s3 = tinys3.Connection(os.environ.get("AWS_ACCESS_KEY_ID"),
                               os.environ.get("AWS_SECRET_ACCESS_KEY"),
                               )
    return s3


connect_s3()


ImageOp = namedtuple("ImageOp", 'function params')


@app.route("/")
def index():
    return "Hello World"


@app.route("/<string:bucket>/<path:path>")
def image_route(bucket, path):
    dirname = os.path.dirname(path)
    name = os.path.basename(path)
    try:
        base, ext = name.split(".")
    except:
        return "no extension specified", 404

    args = get_image_args(request.args)
    params = args.values()
    if params:
        param_name = calculate_new_path(dirname, base, ext, args)
        return get_file_with_params_or_404(bucket, path, param_name, args)
    else:
        return get_file_or_404(bucket, path)


def calculate_new_path(dirname, base, ext, args):
    stuff = [base,]
    stuff.extend(args[key] for key in args if key != 'fm')
 
    format = args.get('fm')
    if format:
        if format == 'png':
            ext = 'png'
        if format == 'jpg' or format == 'jpeg':
            ext = 'jpg'

    filename_with_args = "_".join(str(x) for x in stuff
                               if x is not None) + "." + ext
    # if we enable compression we may want to modify the filename here to include *.gz
    param_name = os.path.join(CACHE_DIR, dirname, filename_with_args)
    return param_name


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
    fm = args.get('fm')
    q = positive_int_or_none(args.get('q'))

    image_args = OrderedDict()
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
    if fm:
        image_args['fm'] = fm
    if q:
        image_args['q'] = q
    return image_args


def get_object_or_none(bucket, path):
    try:
        obj = s3.get(path, bucket=bucket)
    except HTTPError as error:
        if error.response.status_code == 404:
            return None
        else:
            raise
    return obj


@region.cache_on_arguments()
def get_file_or_404(bucket, path):
    key = get_object_or_none(bucket, path)
    if key:
        content_type = key.headers.get('content-type', 'image/jpeg')
        return key.content, 200, {"Content-Type": content_type, "Cache-Control": CACHE_CONTROL}
    else:
        return "404: file '{}' doesn't exist".format(path), 404


def process_image(img, operations):
    #print("compression quality:", img.compression_quality)
    for op in operations:
        #print("op:", op)
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
        if op.function == 'format':
            img.format = op.params['format']
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
                                   'height': params['h'],}
                        )
            )
        else:
            pipeline.append(
                ImageOp('resize', {'width': params['w'],
                                   'height': params['h'],}
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

    fm = params.get('fm')
    if fm == 'png':
        pipeline.append(ImageOp('format', {'format': 'png'}))
    if fm == 'jpg' or fm == 'jpeg':
        pipeline.append(ImageOp('format', {'format': 'jpeg'}))

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


@region.cache_on_arguments()
def get_file_with_params_or_404(bucket, path, param_name, args):
    key = get_object_or_none(bucket, path)
    if key:
        #print("bucket: {}, path {}, param_name {}, args {}".format(bucket, path, param_name, args))
        custom_key = get_object_or_none(bucket, param_name)
        if custom_key:
            #print("processed image already exists")
            content_type = custom_key.headers.get('content-type', "image/jpeg")
            return custom_key.content, 200, {"Content-Type": content_type, "Cache-Control": CACHE_CONTROL}
        else:
            #print("processing image")
            img = Image(blob=BytesIO(key.content))
            format = img.format.lower()
            content_type = "image/{}".format(format)
            size = min(args.get('w', img.size[0]), img.size[0]), min(args.get('h', img.size[1]), img.size[1])
            desired_format = args.get('fm', format)
            print("sizes: {} or {}, formats: {} or {}".format(size, img.size, desired_format, format))
            if size != img.size or desired_format != format:
                img.compression_quality = args.get('q', DEFAULT_QUALITY)
                image = process_image(img, build_pipeline(args))
                format = image.format.lower()
                content_type = "image/{}".format(format)
                temp_handle = image_to_buffer(image, format=format, compress=False)
                s3.upload(param_name, temp_handle, bucket=bucket, content_type=content_type, rewind=True, public=True)
                temp_handle.seek(0)
                return temp_handle.read(), 200, {"Content-Type": content_type, "Cache-Control": CACHE_CONTROL}
            else:
                return key.content, 200, {"Content-Type": content_type, "Cache-Control": CACHE_CONTROL}
    else: 
        return "404: original file '{}' doesn't exist".format(path), 404


if __name__ == "__main__":
    app.run("0.0.0.0", 9876)
