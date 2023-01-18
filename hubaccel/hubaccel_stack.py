from aws_cdk import (
    RemovalPolicy,
    Duration,
    Stack,
    Aws,
    App,
    Tags,
    Environment,
    Duration,
    Stack,
    CfnOutput,
    CfnParameter,
    aws_lambda as lambda_,
    aws_ec2 as ec2,
    aws_ssm as ssm,
    aws_s3 as s3,
    aws_kms as kms,
    aws_iam as iam,
    aws_stepfunctions as step,
    aws_stepfunctions_tasks as step_tasks,
    aws_sns as sns,
    aws_events as events,
    aws_events_targets as event_targets,
)
# from aws_cdk import App, Tags, Environment
import yaml
from constructs import Construct

config=yaml.safe_load(open('config.yml'))

class HubaccelStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # create role for lambda , policy definition below
        # for p in (config['aws_com_serv']['principals']):
        hubaccel_lambda_role = iam.Role(self,
                "hubaccel_lambda_role",
                assumed_by=iam.ServicePrincipal(config['aws_com_serv']['principals'][0]),
                managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
                ],
            )
        
        bucket_encryption_key = kms.Key(self, "hubaccel-encrypt-key",
        alias="hubaccel-encrypt-key",
        enable_key_rotation=True
        )

        # create bucket using KMS encryption
        input_bucket = s3.Bucket(
            self, 
            "input_bucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption_key=bucket_encryption_key,
            lifecycle_rules=[s3.LifecycleRule(
                id="MoveToGlacier",
                enabled=True,
                expiration=Duration.days(config['s3_lifecycle']['expiration_period']),
                noncurrent_version_transitions=[s3.NoncurrentVersionTransition(
                    storage_class=s3.StorageClass.GLACIER,
                    transition_after=Duration.days(config['s3_lifecycle']['noncurrentversion_trans_period'])
                )],
                transitions=[s3.Transition(
                    storage_class=s3.StorageClass.GLACIER,
                    transition_after=Duration.days(config['s3_lifecycle']['glacier_trans_period']),
                )]
            )],
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_PREFERRED,
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # create an SSM parameter for the transform bucket name
        bucket_param = ssm.StringParameter(
            self, "input_bucket_parameter",
            parameter_name="/csvManager/bucket",
            string_value=input_bucket.bucket_name,
            description='HubAccel S3 bucket where Security Hub are exported'
        )

        # create an SSM parameter for the kms Encryption key
        kms_bucket_param = ssm.StringParameter(
            self, "kms_bucket_parameter",
            parameter_name="/csvManager/kms-for-bucket",
            string_value=bucket_encryption_key.key_arn,
            description='hubaccel kms arn for bucket'
        )

        s3_arn            =input_bucket.bucket_arn
        s3_arn_2          =input_bucket.bucket_arn+"/*"

        # creates s3 bucket policy 
        input_bucket.add_to_resource_policy(iam.PolicyStatement(
            effect=iam.Effect.DENY,
            principals=[iam.AnyPrincipal()],
            actions=["s3:*"],
            resources=[s3_arn,s3_arn_2],
            conditions={"Bool": {"aws:SecureTransport": "False"} },
        )

        )
        for p in (config['s3_lifecycle']['principals']):
            input_bucket.add_to_resource_policy(iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                principals=[iam.AccountPrincipal(p)],
                actions=["s3:GetObject*", "s3:ListBucket","s3:PutObject*"],
                resources=[s3_arn,s3_arn_2]
            )
            )

        # creates lambda function
        lambda_function = lambda_.Function(
            self,
            "hubaccel_lambda",
            code=lambda_.Code.from_asset("lambda/exporter"),
            handler="lambda_function.lambda_handler",
            memory_size=512,
            timeout=Duration.seconds(900),
            runtime=lambda_.Runtime.PYTHON_3_9,
            description="Export SecurityHub findings to CSV in S3 bucket",
            role=hubaccel_lambda_role,
            environment={
              "CSV_PRIMARY_REGION" :  f"{config['primary_region']['region']}",
            }
        )    
        Tags.of(lambda_function).add("CodeArchiveKey", f"{config['code_archive']['key']}" )

        # create IAM managed policy for LambdaRole
        managed_policy_lambda = iam.CfnManagedPolicy(self, "hubaccel_lambda_managed_role_policy",
        policy_document=dict(
                Statement=[
                    dict(
                        Action=["iam:GetRole","iam:PassRole","iam:CreateServiceLinkedRole"], 
                        Effect="Allow",
                        Resource=f"arn:aws:iam::{Aws.ACCOUNT_ID}:role/*",
                        Sid="Iam"
                    ),
                    dict(
                        Action=["sts:AssumeRole","sts:GetCallerIdentity"], 
                        Effect="Allow",
                        Resource="*",
                        Sid="Sts"
                    ),
                    dict(
                        Action=["s3:PutObject","s3:GetObject"], 
                        Effect="Allow",
                        Resource=[s3_arn,s3_arn_2],
                        Sid="S3"
                    ),
                    dict(
                        Action=["securityhub:GetFindings","securityhub:BatchUpdateFindings"], 
                        Effect="Allow",
                        Resource="*",
                        Sid="SecurityHub"
                    ),
                    dict(
                        Action=["kms:Describe*","kms:Decrypt","kms:GenerateDataKey"], 
                        Effect="Allow",
                        Resource=f"{bucket_encryption_key.key_arn}",
                        Sid="KMSDecrypt"
                    ),
                    dict(
                        Action=["lambda:InvokeFunction"], 
                        Effect="Allow",
                        Resource=f"{lambda_function.function_arn}",
                        Sid="Lambda"
                    ),
                    dict(
                        Action=["ec2:CreateNetworkInterface","ec2:DescribeNetworkInterfaces","ec2:DeleteNetworkInterface"], 
                        Effect="Allow",
                        Resource=f"{lambda_function.function_arn}",
                        Sid="EC2"
                    ),
                    dict(
                        Action=["ssm:PutParameter","ssm:GetParameters"], 
                        Effect="Allow",
                        Resource=f"arn:aws:ssm:{Aws.REGION}:{Aws.ACCOUNT_ID}:parameter/csvManager/*",
                        Sid="SMS"
                    ),
                ],
                Version="2012-10-17",
            ),
        description="Allow Lambda, EC2, and SSM to carry out necessary operations",
        managed_policy_name="CsvManagerForSecurityHub",
        roles=[hubaccel_lambda_role.role_name]
        )    

