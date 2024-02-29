import json
import os
os.environ["GIT_PYTHON_REFRESH"] = "quiet"
import git
from git import Repo, Actor
import sys
import shutil
import boto3
import yaml
from datetime import datetime
import os.path

def lambda_handler(event, context):
# note: must be updated by client
    git_user        ='git_user+1-at-670927383464'
    git_password    ='64gSqV5jXnDYu0rtlNW4Q9qeCjH9Ulg4gFri1HsBNXY='
    ssm=boto3.client('ssm')
    git_target = (ssm.get_parameter(Name='/codecommit-cdk/repository-ssh')['Parameter']['Value']).lstrip('ssh://')
    git_staging = (ssm.get_parameter(Name='/codecommit-cdk/repository-ssh-staging')['Parameter']['Value']).lstrip('ssh://')
    git_url_staging =f"https://{git_user}:{git_password}@{git_staging}"
    git_url_target  =f"https://{git_user}:{git_password}@{git_target}"
    if os.path.isdir('/tmp/pipeline'):
        shutil.rmtree('/tmp/pipeline')
    empty_repo = git.Repo.init('/tmp/pipeline')
    origin = empty_repo.create_remote('origin', git_url_staging)
    assert origin.exists()
    assert origin == empty_repo.remotes.origin == empty_repo.remotes['origin']
    origin.fetch()
    empty_repo.create_head('main', origin.refs.main).set_tracking_branch(origin.refs.main).checkout()
    origin.rename('new_origin')
    origin.pull()
    file_path=(event['file_path'])
    yaml_name=(event['yaml_name'])
    role_arn=(event['role_arn'])
    vpc_id=(event['vpc_id'])
    private=(event['private'])
    action=(event['action'])
    zone_dict={"Zone" : {
        "file_path" : file_path,
        "yaml_name" : yaml_name,
        "role_arn"  : role_arn,
        "private"  : private,
        "vpc_id"  : vpc_id,
        "action"  : action,
        }
    }
    f = open(f"/tmp/pipeline/input.yaml", "w+")
    yaml.dump(zone_dict, f, allow_unicode=True)
    now = datetime.now()
    date_time = now.strftime("%m%d%Y%H%M%S")
    commit_message= f"code-added-{date_time}"
    empty_repo.create_remote('origin', url=git_url_target)
    empty_repo.index.add("input.yaml")
    author = Actor("An author", "author@example.com")
    empty_repo.index.commit(commit_message, author=author)
    empty_repo.remote('origin').push(force=True,refspec='{}:{}'.format('main', 'main'))
