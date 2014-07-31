import os
from os.path import join
from datetime import datetime
import subprocess

import boto
from fabric.api import cd, env, run, task
from fabtools import service
from fabtools.python import virtualenv
import hammock


CLOUD_APP = "giraffe"
APP_DIR = "/opt/app"
VIRTUAL_ENV = join(APP_DIR, "env")
SERVICE_NAME = "giraffe"
GIT_REPO = "git@github.com:steder/giraffe.git"
DEV_PHASES = ["beta", "staging", "production"]
DEV_PHASE = "staging"

AWS_ACCOUNT_NUMBER = os.environ.get("AWS_ACCOUNT_NUMBER")
LOAD_BALANCER_NAME = "{}-staging".format(CLOUD_APP)
SNS_ARN = "arn:aws:sns:us-east-1:{}:{}".format(AWS_ACCOUNT_NUMBER, CLOUD_APP)

SERVER_USER = "ubuntu"
KEY_NAME = os.environ.get("KEY_NAME")
SSH_KEY_FILE = KEY_NAME if os.path.exists(KEY_NAME) else os.path.expanduser("~/.ssh/{}".format(KEY_NAME))

ASGARD_HOST = os.environ.get("ASGARD_HOST")
ASGARD_CRED_FILE = "{}/.asgard/credentials".format(os.getenv("HOME"))
ASGARD_CREDENTIALS = (line[:-1] for line in open(ASGARD_CRED_FILE, "r").readlines())

env.forward_agent = True
env.key_filename = SSH_KEY_FILE
env.user = SERVER_USER
env.connection_attempts = 5


def aws_hosts(lb=LOAD_BALANCER_NAME):
    # This assumes your bash_profile has
    # AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY set.

    # Get a list of instance IDs for the ELB.
    instances = []
    conn = boto.connect_elb()
    for elb in conn.get_all_load_balancers(lb):
        instances.extend(elb.instances)

    # Get the instance IDs and public dns for the reservations.
    conn = boto.connect_ec2()
    reservations = conn.get_all_instances([i.id for i in instances])
    instance_ids = []
    for reservation in reservations:
        for i in reservation.instances:
            instance_ids.append((i.id, i.private_ip_address, i.tags.get('aws:autoscaling:groupName')))
    instance_ids.sort()  # Put the tuples in some sort of order

    # Get the public CNAMES for those instances.
    hosts = [node[1] for node in instance_ids]

    return hosts, instance_ids[0][0], instance_ids[0][2]


def autoscale_group_hosts(group_name):
    import boto.ec2
    from boto.ec2.autoscale import AutoScaleConnection
    ec2 = boto.connect_ec2()
    conn = AutoScaleConnection()
    groups = conn.get_all_groups(names=[])
    groups = [ group for group in groups if group.name.startswith(group_name) ]

    instance_ids = []
    instances = []
    for group in groups:
        print group.name
        instance_ids.extend([i.instance_id for i in group.instances])
        instances.extend(ec2.get_only_instances(instance_ids))

    return [i.private_ip_address for i in instances], instances[0].id, instances[0].tags.get("aws:autoscaling:groupName")


def is_git_tag(ref):
    lines = subprocess.check_output(['git', 'show-ref', ref])
    return 'refs/tags' in lines


def update_code(tag):
    with cd(APP_DIR):
        run('find . -name "*.pyc" -print -delete')
        run("git fetch", pty=False)
        run("git reset --hard")
        run("git checkout " + str(tag))
        if not is_git_tag(tag):
            run("git pull")


def build_app():
    with cd(APP_DIR):
        with virtualenv(VIRTUAL_ENV):
            run("pip install -U -r requirements.txt")


def restart_app(service_name=SERVICE_NAME):
    if service.is_running(SERVICE_NAME):
        service.restart(SERVICE_NAME)
    else:
        service.start(SERVICE_NAME)


def publish_to_sns(message, subject):
    print(subject)
    print(message)
    boto.connect_sns().publish(SNS_ARN, message, subject)


def make_ami(tag):
    date = datetime.utcnow().isoformat().replace(":", "").split(".")[0]
    image_name = "{}-{}_{}".format(CLOUD_APP, tag, date)
    print "Snapshotting instance {} [{}] to image {}".format(INSTANCE_ID, INSTANCE_CLUSTER, image_name)
    conn = boto.connect_ec2()
    ami = conn.create_image(INSTANCE_ID, image_name, description=date)
    message = "AMI:\n  {}\nAMI Name:\n  {}".format(ami, image_name)
    subject = "AMI Created for {}".format(CLOUD_APP)
    publish_to_sns(message, subject)
    return ami, image_name


def deploy_next_asg(ami):
    asgard = hammock.Hammock(ASGARD_HOST, auth=tuple(ASGARD_CREDENTIALS))
    cluster = "{}-d0staging".format(CLOUD_APP)
    current_asg = asgard("us-east-1").cluster.show(cluster + ".json").GET().json()[0]["autoScalingGroupName"]
    param_dict = {"name": cluster, "imageId": ami, "trafficAllowed": "true"}
    next_asg = asgard("us-east-1").cluster.createNextGroup.POST(params=param_dict)
    if next_asg.status_code == 200:
        task = next_asg.url.split("/")[-1]
        status = ""
        while status not in ["completed", "failed"]:
            next_asg_result = asgard("us-east-1").task.show("{}.json".format(task)).GET().json()
            status = next_asg_result["status"]

        # only delete the asg if we were able to create the new one successfully

        delete_asg_log = ""
        delete_asg_result = ""
        if status == "completed":
            delete_asg = asgard("us-east-1").cluster.delete.POST(params={"name": current_asg})
            if delete_asg.status_code == 200:
                task = delete_asg.url.split("/")[-1]
                status = ""
                while status not in ["completed", "failed"]:
                    delete_asg_result = asgard("us-east-1").task.show("{}.json".format(task)).GET().json()
                    status = delete_asg_result["status"]

            if delete_asg_result["log"]:
                delete_asg_log = "\n".join(i for i in delete_asg_result["log"])

        if next_asg_result["log"]:
            next_asg_log = "\n".join(i for i in next_asg_result["log"])

        message = next_asg_log + "\n\n" + delete_asg_log
        subject = "Asgard results for {}-{}".format(CLOUD_APP)
        publish_to_sns(message, subject)
    return True


# Set hosts to the defaults (giraffe-staging)
env.hosts, INSTANCE_ID, INSTANCE_CLUSTER = aws_hosts()
print env.hosts, INSTANCE_ID, INSTANCE_CLUSTER


def set_environment(env_name="staging"):
    global DEV_PHASE, INSTANCE_ID, INSTANCE_CLUSTER
    DEV_PHASE = env_name
    group = "{}-d0{}".format(CLOUD_APP, env_name)
    print 'autoscale group name', group
    env.hosts, INSTANCE_ID, INSTANCE_CLUSTER = autoscale_group_hosts(group)
    print "hosts:", env.hosts


# Tweak which boxes you run commands on:
#
#   fab production hostnames
@task
def beta():
    """
    By default we point every fab command at staging so this is
    only necessary if you're feeling pedantic.

    """
    set_environment(env_name="beta")


@task
def staging():
    """
    By default we point every fab command at staging so this is
    only necessary if you're feeling pedantic.

    """
    set_environment(env_name="staging")


@task
def production():
    """
    By default we're pointed at the staging box but if you
    really want to run a command on production you can do:

      $ fab production <command>

    As an example we include 2 fab "targets":

      $ fab production hostname

    And

      $ fab production restart

    """
    set_environment(env_name="production")


@task
def deploy(tag="master"):
    update_code(tag)
    build_app()
    restart_app()
    if tag != "master":
        ami, image_name = make_ami(tag)
        deploy_next_asg(ami)


@task
def inplace_deploy(tag="master"):
    update_code(tag)
    build_app()
    restart_app()


@task
def hostname():
    run('hostname')


@task
def restart():
    restart_app()
