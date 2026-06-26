"""Cognito Auth Stack — provisions Cognito User Pool + API Gateway HTTP API with JWT Authorizer.

Full implementation in task 4.2 (Cognito) and task 4.3 (API Gateway).
"""

import aws_cdk as cdk
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk.aws_apigatewayv2 import (
    CorsPreflightOptions,
    CorsHttpMethod,
    HttpApi,
    HttpMethod,
    HttpNoneAuthorizer,
    VpcLink,
)
from aws_cdk.aws_apigatewayv2_authorizers import HttpJwtAuthorizer
from aws_cdk.aws_apigatewayv2_integrations import HttpAlbIntegration
from constructs import Construct


class CognitoAuthStack(cdk.Stack):
    """Provisions Cognito User Pool and API Gateway HTTP API with JWT Authorizer."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- Cognito User Pool (task 4.2) ---
        self.user_pool = cognito.UserPool(
            self,
            "AwaasAIUserPool",
            user_pool_name="awaasai-user-pool",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            user_verification=cognito.UserVerificationConfig(
                email_subject="Awaas AI - Verify your email",
                email_body="Your verification code is {####}",
                email_style=cognito.VerificationEmailStyle.CODE,
            ),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_uppercase=True,
                require_lowercase=True,
                require_digits=True,
                require_symbols=True,
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # --- Hosted UI Domain (task 4.2) ---
        domain_prefix = self.node.try_get_context("cognito_domain_prefix") or "awaasai-auth"
        self.user_pool_domain = self.user_pool.add_domain(
            "AwaasAIUserPoolDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=domain_prefix,
            ),
        )

        # --- App Client with SRP + Refresh flows (task 4.2) ---
        self.user_pool_client = self.user_pool.add_client(
            "AwaasAIAppClient",
            user_pool_client_name="awaasai-app-client",
            auth_flows=cognito.AuthFlow(
                user_srp=True,
                custom=False,
                user_password=False,
                admin_user_password=False,
            ),
            generate_secret=False,
            prevent_user_existence_errors=True,
            access_token_validity=cdk.Duration.hours(1),
            id_token_validity=cdk.Duration.hours(1),
            refresh_token_validity=cdk.Duration.days(30),
        )

        # --- API Gateway HTTP API with JWT Authorizer (task 4.3) ---

        # Look up existing VPC by context parameter
        vpc_id = self.node.try_get_context("vpc_id")
        if not vpc_id:
            raise ValueError(
                "CDK context 'vpc_id' is required. "
                "Pass via -c vpc_id=vpc-xxx or cdk.json context."
            )

        vpc = ec2.Vpc.from_lookup(self, "ExistingVpc", vpc_id=vpc_id)

        # Look up existing ALB listener by ARN from context
        alb_listener_arn = self.node.try_get_context("alb_listener_arn")
        if not alb_listener_arn:
            raise ValueError(
                "CDK context 'alb_listener_arn' is required. "
                "Pass via -c alb_listener_arn=arn:aws:... or cdk.json context."
            )

        alb_listener = elbv2.ApplicationListener.from_application_listener_attributes(
            self,
            "ExistingAlbListener",
            listener_arn=alb_listener_arn,
            security_group=ec2.SecurityGroup.from_security_group_id(
                self,
                "AlbSg",
                self.node.try_get_context("alb_security_group_id") or "sg-placeholder",
            ),
        )

        # VPC Link for private integration with ALB
        vpc_link = VpcLink(
            self,
            "AwaasAIVpcLink",
            vpc=vpc,
            vpc_link_name="awaasai-vpc-link",
        )

        # ALB integration via VPC Link
        alb_integration = HttpAlbIntegration(
            "AlbIntegration",
            listener=alb_listener,
            vpc_link=vpc_link,
        )

        # JWT Authorizer referencing Cognito User Pool
        issuer_url = (
            f"https://cognito-idp.{self.region}.amazonaws.com/"
            f"{self.user_pool.user_pool_id}"
        )

        jwt_authorizer = HttpJwtAuthorizer(
            "CognitoJwtAuthorizer",
            jwt_issuer=issuer_url,
            jwt_audience=[self.user_pool_client.user_pool_client_id],
        )

        # HTTP API with CORS configuration
        self.http_api = HttpApi(
            self,
            "AwaasAIHttpApi",
            api_name="awaasai-http-api",
            cors_preflight=CorsPreflightOptions(
                allow_origins=["*"],
                allow_methods=[
                    CorsHttpMethod.GET,
                    CorsHttpMethod.POST,
                    CorsHttpMethod.PUT,
                    CorsHttpMethod.DELETE,
                    CorsHttpMethod.OPTIONS,
                ],
                allow_headers=["Authorization", "Content-Type"],
            ),
            default_authorizer=jwt_authorizer,
            default_integration=alb_integration,
        )

        # Health-check routes WITHOUT authorizer
        self.http_api.add_routes(
            path="/health",
            methods=[HttpMethod.GET],
            integration=alb_integration,
            authorizer=HttpNoneAuthorizer(),
        )

        self.http_api.add_routes(
            path="/services/health",
            methods=[HttpMethod.GET],
            integration=alb_integration,
            authorizer=HttpNoneAuthorizer(),
        )

        # --- Stack Outputs ---
        cdk.CfnOutput(
            self,
            "UserPoolId",
            value=self.user_pool.user_pool_id,
            description="Cognito User Pool ID",
            export_name="AwaasAI-UserPoolId",
        )

        cdk.CfnOutput(
            self,
            "AppClientId",
            value=self.user_pool_client.user_pool_client_id,
            description="Cognito App Client ID",
            export_name="AwaasAI-AppClientId",
        )

        cdk.CfnOutput(
            self,
            "HostedUIDomain",
            value=self.user_pool_domain.domain_name,
            description="Cognito Hosted UI Domain",
            export_name="AwaasAI-HostedUIDomain",
        )

        cdk.CfnOutput(
            self,
            "ApiGatewayUrl",
            value=self.http_api.url or "",
            description="API Gateway HTTP API URL",
            export_name="AwaasAI-ApiGatewayUrl",
        )
