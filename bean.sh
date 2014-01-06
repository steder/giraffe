#!/usr/bin/env bash

<<EOH

create an archive for elastic beanstalk

EOH

#TAG="v1.0.0"
TAG="HEAD"

# git tag $TAG
git archive --format=zip $TAG > giraffe-$TAG.zip
