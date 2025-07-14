"""
You'll need to set these environment variables:

 - AWS_ACCESS_KEY_ID
 - AWS_SECRET_ACCESS_KEY

I'd recommend setting them in your ``app.sh`` file.

"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from collections import namedtuple
from collections import OrderedDict
from io import BytesIO
import gzip
import hashlib
import hmac
import os
import re

from flask import Flask
from flask import request
from flask import render_template
from PIL import Image as PillowImage
from requests.exceptions import HTTPError, ConnectionError
import requests
import six
from six.moves.urllib import parse
import tinys3
import wand
from wand.color import Color
from wand.font import Font
from wand.image import Image
from werkzeug.exceptions import BadRequest

FORMAT_MAP = {
    'png': {
        'extension': 'png',
        'format': {'format': 'png'},
    },
    'jpg': {
        'extension': 'jpg',
        'format': {'format': 'jpeg'},
    },
    'eps': {
        'extension': 'eps',
        'format': {'format': 'eps'},
    },
}

FORMAT_MAP['jpeg'] = FORMAT_MAP['jpg']


app = Flask(__name__)
ENV = os.environ.get("ENV", "development").lower()
if ENV == "production":
    app.debug = False
elif ENV == "staging":
    app.debug = False
else:
    app.debug = True
CACHE_URLS = os.environ.get("MEMCACHED").split(";") if os.environ.get("MEMCACHED") else []

SECRET = os.environ.get("GIRAFFE_SECRET", "0x24FEEDFACEDEADBEEFCAFE")

s3 = None
CACHE_DIR = os.environ.get("GIRAFFE_CACHE_DIR", 'giraffe')
CACHE_CONTROL = "max-age=2592000"
DEFAULT_QUALITY = 75
MAX_WIDTH = 7680
MAX_HEIGHT = 4320
MAX_PIXELS = MAX_WIDTH * MAX_HEIGHT # 8K resolution is pretty damn big


def get_image_size(bytes):
    img = PillowImage.open(BytesIO(bytes))
    width, height = img.size
    return width, height


def connect_s3():
    global s3
    if not s3:
        s3 = tinys3.Connection(os.environ.get("AWS_ACCESS_KEY_ID"),
                               os.environ.get("AWS_SECRET_ACCESS_KEY"),
                               )
    return s3


connect_s3()


ImageOp = namedtuple("ImageOp", 'function params')


# Lookup table for JPEG extensions (more secure than regex)
JPEG_EXTENSIONS = {'jpe', 'jpg', 'jpeg'}


def sanitize_extension(ext):
    """
    Sanitize extension input to prevent security issues.
    Only allow alphanumeric characters and limit length.
    """
    if not ext:
        return ""
    # Remove leading dot and convert to lowercase
    ext = ext.lower().strip(".")
    # Only allow alphanumeric characters and limit to reasonable length
    if not ext.isalnum() or len(ext) > 10:
        return ""
    return ext


def extension_to_format(ext):
    """
    Punch possible extensions into a common format string

     e.g.:

      .jpg -> jpg
      .JPG -> jpg
      jpe  -> jpg
      JPE  -> jpg
      JPEG -> jpg

    """
    sanitized_ext = sanitize_extension(ext)
    if not sanitized_ext:
        raise ValueError(f"Invalid extension: '{ext}'")
    if sanitized_ext in JPEG_EXTENSIONS:
        return "jpg"
    return sanitized_ext


def normalize_mimetype(ext):
    """
    Punch possible extensions into a common format string

     e.g.:

      .jpg -> jpeg
      .JPG -> jpeg
      jpe  -> jpeg
      JPE  -> jpeg
      JPEG -> jpeg

    """
    sanitized_ext = sanitize_extension(ext)
    if sanitized_ext in JPEG_EXTENSIONS:
        return "jpeg"
    return sanitized_ext


def path_to_format(path):
    name, ext = os.path.splitext(os.path.basename(path))
    return extension_to_format(ext)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/placeholders/<string:filename>")
def placeholder_it(filename, message=None):
    bg = '#' + request.args.get('bg', 'fff')
    filename = filename.lower()
    basename, ext = os.path.splitext(filename)
    ext = ext.strip(".")
    width, height = basename.split("x")
    width, height = int(width), int(height)
    content_type = 'image/{}'.format(normalize_mimetype(ext))

    if ext in ('jpg', 'jpeg'):
        fmt = 'jpg'
    elif ext == 'png':
        fmt = 'png'
    else:
        return "I don't know how to handle format .{} files".format(ext), 404

    if message:
        text = message
    else:
        text = '{}x{}'.format(width, height)
    min_font_ratio = width / (len(text) * 12.0)
    size = max(16 * (height / 100), 16 * min_font_ratio)

    font = Font(path='fonts/Inconsolata-dz-Powerline.otf', size=size)
    c = Color(bg) if fmt == "jpg" else None
    with Image(width=width, height=height, background=c) as image:
        image.caption(text, left=0, top=0,
                      font=font,
                      gravity="center")
        buff = image_to_buffer(image, fmt=ext, compress=False)
        buff.seek(0)
        return buff.read(), 200, {"Content-Type": content_type, "Cache-Control": CACHE_CONTROL}


def generate_hmac(url):
    return hmac.new(SECRET, url, hashlib.sha1).hexdigest()


@app.route("/proxy/<string:image_hmac>")
def proxy_that_stuff(image_hmac):
    """
    How do we handle non-ssl content image urls in the forums?

    The same way github does!  Rewrite the img tags in the forums from:

        <img src="http://example.com/image.jpg">

    To:

        <img src="https://<giraffe>.cloudfront.net/proxy/<HMAC>?url=http://example.com/image.jpg">

    HMAC is a hash of a shared secret and the URL using SHA1.

    So in whatever generates the forum markup you need to have the same SECRET as
    your deployed Giraffe instance(s).  Then you need to generate a hex digest from
    the URL with that secret.  (See `generate_hmac` above for an example)

    """

    url = request.args.get("url")
    if not url:
        return "Oh noes, you didn't give me a url", 404
    """
    Before we just go off and get this image let's make sure the hmac we've
    got actually matches.
    """
    expected_hmac = generate_hmac(url)
    if expected_hmac != image_hmac:
        return "Oh noes, your key doesn't match!", 404

    resp = requests.get(url)
    return resp.content, 200, {"Content-Type": resp.headers['content-type'], "Cache-Control": CACHE_CONTROL}


@app.route("/<string:bucket>/<path:path>")
def image_route(bucket, path):
    dirname = os.path.dirname(path)
    name = os.path.basename(path)
    try:
        base, ext = name.split(".")
    except Exception:
        return "no extension specified", 404


    force = request.args.get("force", False)
    args = get_image_args(request.args)
    params = args.values()
    if params:
        param_name = calculate_new_path(dirname, base, ext, args)
        return get_file_with_params_or_404(bucket, path, param_name, args, force)
    else:
        return get_file_or_404(bucket, path)


def calculate_new_path(dirname, base, ext, args):
    stuff = [base,]
    for key, val in args.items():
        if key == "fm":
            continue
        if val is not None:
            if isinstance(val, six.string_types):
                # escape special characters in URLs for overlay / mask arguments
                val = parse.quote_plus(val)
            stuff.append("{}{}".format(key, val))

    fmt = args.get('fm')
    if fmt:
        ext = FORMAT_MAP[fmt]['extension']

    filename_with_args = "_".join(str(x) for x in stuff) + "." + ext
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
    bg = args.get('bg')
    overlay = args.get('overlay')
    ox = args.get('ox')
    oy = args.get('oy')
    ow = args.get('ow')
    oh = args.get('oh')

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
    if overlay:
        image_args['overlay'] = overlay
    if ox:
        image_args['ox'] = int(ox)
    if oy:
        image_args['oy'] = int(oy)
    if ow:
        image_args['ow'] = int(ow)
    if oh:
        image_args['oh'] = int(oh)
    if bg:
        image_args['bg'] = bg

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


def get_file_or_404(bucket, path):
    key = get_object_or_none(bucket, path)
    if key:
        content_type = key.headers.get('content-type', 'image/jpeg')
        return key.content, 200, {"Content-Type": content_type, "Cache-Control": CACHE_CONTROL}
    else:
        return "404: file '{}' doesn't exist".format(path), 404


def overlay_that(img, bucket=None, path=None, overlay=None, bg=None, w=None, h=None, x=None, y=None):
    if bucket:
        key = get_object_or_none(bucket, path)
        overlay_content = key.content
    else:
        try:
            resp = requests.get(overlay)
        except (ConnectionError) as e:
            print(e)
            raise
        else:
            overlay_content = resp.content

    if overlay_content:
        if w is not None and h is not None and x is not None and y is not None:
            pass
        else:
            w, h, x, y = 294, 336, 489, 173

        image_orientation = 'square'
        overlay_orientation = 'square'

        if img.width > img.height:
            image_orientation = 'landscape'
        elif img.width < img.height:
            image_orientation = 'portrait'

        overlay_img = stubbornly_load_image(overlay_content, None, None)

        if overlay_img.width > overlay_img.height:
            overlay_orientation = 'landscape'
        elif overlay_img.width < overlay_img.height:
            overlay_orientation = 'portrait'

        overlay_width, overlay_height = overlay_img.width, overlay_img.height
        width, height = w, h
        size = "{}x{}^".format(width, height)
        #crop_size = "{}x{}!".format(width, height)
        img.transform(resize=size)
        #w_offset = max((img.width - width) / 2, 0)
        #h_offset = max((img.height - height) / 2, 0)
        c = Color('#' + bg)
        background = Image(width=overlay_width, height=overlay_height, background=c)
        background.composite(img, x, y)
        img = background

        # Overlay canvas:
        img.composite(overlay_img, 0, 0)
    else:
        raise Exception("Couldn't find an overlay file for bucket '{}' and path '{}' (overlay='{}')".format(bucket, path, overlay))
    return img


def process_image(img, operations):
    for op in operations:
        if callable(op.function):
            img = op.function(img, **op.params)
        if op.function == 'resize':
            if not op.params.get('width'):
                if img.animation:
                    width, height = img.size
                    img.resize(width, op.params['height'])
                else:
                    size = "x{}".format(op.params['height'])
                    img.transform(resize=size)
            elif not op.params.get('height'):
                if img.animation:
                    width, height = img.size
                    img.resize(op.params['width'], height)
                else:
                    size = "{}".format(op.params['width'])
                    img.transform(resize=size)
            else:
                # this is my attempt at ResizeToFit from PILKit:
                if img.animation:
                    img.resize(op.params['width'], op.params['height'])
                else:
                    size = "{}x{}^".format(op.params['width'], op.params['height'])
                    crop_size = "{}x{}!".format(op.params['width'], op.params['height'])
                    img.transform(resize=size)
                    w_offset = max((img.width - op.params['width']) / 2, 0)
                    h_offset = max((img.height - op.params['height']) / 2, 0)
                    geometry = "{}+{}+{}".format(crop_size, w_offset, h_offset)
                    img.transform(crop=geometry)
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
        if op.function == 'rotate':
            img.rotate(op.params['degrees'])

    return img


def fit_crop(img, width=None, height=None, anchor=None):
    # regarding offset: based on anchor being 'top', 'bottom', 'left', 'right'
    # we should adjust offset.  By default this empty offset
    # means we will always crop to the center.
    offset = ''
    if anchor == 'top':
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
    elif 'h' in params:
        pipeline.append(
            ImageOp('resize', {'height': params["h"]})
        )
    elif 'w' in params:
        pipeline.append(
            ImageOp('resize', {'width': params["w"]})
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

    rot = params.get('rot', None)
    if rot:
        rot = positive_int_or_none(rot)
        if rot is None or rot >= 360:
            raise BadRequest(description='"%s" is not a valid rotation value' % str(rot))

        pipeline.append(
            ImageOp('rotate', {'degrees': int(rot)})
        )

    fm = params.get('fm')
    if fm:
        pipeline.append(ImageOp('format', FORMAT_MAP[fm]['format']))

    overlay = params.get('overlay', None)
    if overlay:
        bg = params.get('bg', '0FFF')
        segments = overlay.split("/")
        bucket = segments[1]
        path = "/" + "/".join(segments[2:])

        # order matters, I think we want to do this first, then resize or flip:
        # TODO: consider allowing the order arguments are specified on the URL
        # influence the order in which they are applied.
        pipeline.insert(0, ImageOp(
            overlay_that,
            {'overlay': overlay,
             'bucket': bucket,
             'path': path,
             'bg': bg,
             'x': params.get('ox', None),
             'y': params.get('oy', None),
             'w': params.get('ow', None),
             'h': params.get('oh', None),
         }
        ))
    return pipeline


def image_to_buffer(img, fmt='JPEG', compress=False):
    buff = BytesIO()
    img.format = fmt
    if compress:
        filename, mode, compresslevel, mtime = '', 'wb', 9, None
        gz = gzip.GzipFile(filename, mode, compresslevel, buff, mtime)
        img.save(file=gz)
    else:
        img.save(file=buff)
    return buff


def image_to_binary(img, fmt='JPEG'):
    return img.make_blob(fmt)

def stubbornly_load_image(content, headers, path):
    try:
        return Image(blob=BytesIO(content))
    except wand.exceptions.MissingDelegateError as orig_e:
        try:
            return Image(blob=BytesIO(content), format='ico')
        except wand.exceptions.MissingDelegateError:
            raise orig_e


def get_file_with_params_or_404(bucket, path, param_name, args, force):
    key = get_object_or_none(bucket, path)
    if key:
        if force:
            custom_key = None
        else:
            custom_key = get_object_or_none(bucket, param_name)

        if custom_key:
            content_type = custom_key.headers.get('content-type', "image/jpeg")
            return custom_key.content, 200, {"Content-Type": content_type, "Cache-Control": CACHE_CONTROL}
        else:
            width, height = get_image_size(key.content)
            # If the original image is larger than 4K resolution we ain't resizing
            # it as it would likely require too much memory / time
            if (width * height) > MAX_PIXELS:
                width, height = min(args.get('w', width), width), min(args.get('h', height), height)
                return placeholder_it("{}x{}.jpg".format(width, height))
            img = stubbornly_load_image(key.content, key.headers, path)
            fmt = img.format.lower()

            default_format = path_to_format(path)

            size = args.get('w', img.size[0]), args.get('h', img.size[1])
            if (size[0] * size[1]) > MAX_PIXELS:
                return placeholder_it("{}x{}.jpg".format(640, 640), "TOO BIG")


            content_type = "image/{}".format(normalize_mimetype(fmt))
            desired_format = args.get('fm', default_format)

            pipeline = build_pipeline(args)

            if (size != img.size or desired_format != fmt or args.get('q', None) is not None
                or len(pipeline) > 0):
                # if the desired size, format, quality, or if there are any pipeline operations
                # to do like flipping the image then we should do something, otherwise we'll
                # just return the image unchanged from s3.
                img.compression_quality = args.get('q', DEFAULT_QUALITY)
                image = process_image(img, pipeline)
                fmt = image.format.lower()
                content_type = "image/{}".format(normalize_mimetype(desired_format))
                temp_handle = image_to_buffer(image, fmt=desired_format, compress=False)
                s3.upload(param_name, temp_handle, bucket=bucket, content_type=content_type, rewind=True, public=True)
                temp_handle.seek(0)
                return temp_handle.read(), 200, {"Content-Type": content_type, "Cache-Control": CACHE_CONTROL}
            else:
                return key.content, 200, {"Content-Type": content_type, "Cache-Control": CACHE_CONTROL}
    else:
        return "404: original file '{}' doesn't exist".format(path), 404


if __name__ == "__main__":
    app.run("0.0.0.0", 9876)
