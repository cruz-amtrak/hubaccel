#!/usr/bin/env python3
import os

import aws_cdk as cdk
from aws_cdk import App, Tags, Environment
import yaml

from hubaccel.hubaccel_stack import HubaccelStack

config=yaml.safe_load(open('config.yml'))

env_main = cdk.Environment(
    #account=config['env']['id'], 
    account=os.environ.get("CDK_DEPLOY_ACCOUNT", os.environ["CDK_DEFAULT_ACCOUNT"]),    
    region=config['env']['region']
    )

app = cdk.App()
HubaccelStack(app, 
    "HubaccelStack",
    env=env_main
    )

app.synth()
