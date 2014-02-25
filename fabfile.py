import boto
from fabric.api import cd, env, run, task

name_tag = "giraffe"


def get_hosts():
    global instances
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
    with cd('giraffe'):
        run('git pull')
    run('sudo service giraffe restart')
    run('sudo service giraffe status')
    run('echo "deployed!"')
