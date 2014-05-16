import os

import boto
from fabric.api import cd, env, prefix, run, task
from fabric.operations import put

name_tag = "giraffe"


def get_hosts():
    ec2 = boto.connect_ec2()
    hosts = []
    for i in ec2.get_only_instances():
        if i.tags.get("Name") == name_tag:
            hosts.append("{}@{}".format(
                "ubuntu", i.private_ip_address
            ))
    print "hosts:", hosts
    return hosts


env.hosts = get_hosts()
env.forward_agent = True


@task
def deploy():
    run('echo "deploying..."')
    run('uname -s')
    run('ls')
    run('sudo service giraffe status')
    if os.path.exists('conf.sh'):
        put('conf.sh', 'giraffe')
    else:
        print "Couldn't find a local 'conf.sh' file to load to set giraffe service environment variables (see the app.sh file)"
    with cd('giraffe'):
        run('find . -name "*.pyc" -print -delete')
        run('git checkout master')
        run('git pull')
        with prefix('source /opt/app/env/bin/activate'):
            run('pip install -U -r requirements.txt')

    run('sudo service giraffe restart')
    run('sudo service giraffe status')
    run('echo "deployed!"')
