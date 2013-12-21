# Giraffe

Image pipelines are hard; let's go ride bikes!

## WTF?

The names will change.

## About

`this fledgling project` is an image processing proxy with the immediate
goal of being placed between an S3 bucket and a cloudfront distribution.

## Overview of architecture:

You store original images in an s3 bucket.  Something like:

```
s3://media.example.com/profile_pictures/1.jpg
```

You set up `this thing` in ec2 behind an elb, point dns like `images.example.com` at it,
and configure it to point to your bucket.

Finally set up a new `cloudfront` distribution (e.g.: `hash.cloudfront.net`) to sit 
in front of `images.example.com` and be sure to set it to forward query strings
to origin.

### Example

Assuming you `1.jpg` above is a 1080p image and you'd really like to just display
a 100x100 thumbnail next to `user_1`'s comments you can do so easily by simply including the following in your markup:

```
<img src="http://hash.cloudfront.net/profile_pictures/1.jpg?w=100&h=100"
     alt="profile pic" title="user_1" />
```

The request will hit cloudfront, which will turn around and hit your origin at 
`images.example.com`, which will check for an image `/profile_pictures/1.jpg`, if that exists it'll then check for the requested size image at `/cache/profile_pictures/1_100_100.jpg` in `s3://media.example.com`.  If it finds it
it will simply return it, otherwise it'll use the original to generate the 
`cache` prefixed resized version.

## TODO

 - handle nonsensical requests for images (resizing larger than the bounds of the original, etc)
 - handle crops and fits
 - optimize performance by caching image existence checks (finally a use for bloom filters?)
 - `pypy`?
 - `wand` / `imagemagick` instead of pil?


