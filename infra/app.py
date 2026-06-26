#!/usr/bin/env python3
"""CDK app entry point for the Cognito Auth Layer stack."""

import aws_cdk as cdk

from cognito_auth_stack import CognitoAuthStack

app = cdk.App()

CognitoAuthStack(
    app,
    "CognitoAuthStack",
    env=cdk.Environment(
        account=app.node.try_get_context("account"),
        region=app.node.try_get_context("region") or "ap-south-1",
    ),
    description="Cognito User Pool and API Gateway JWT Authorizer for Awaas AI",
)

app.synth()
