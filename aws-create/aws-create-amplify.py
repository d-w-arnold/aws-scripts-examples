import base64
import json
import logging
import os
import sys
from datetime import datetime
from urllib.parse import urlparse

import validators
from botocore.exceptions import ClientError
from pytz import timezone

sys.path.append(os.path.dirname(os.getcwd()))

# pylint: disable=wrong-import-position
from aws_service_name import AwsServiceName as aws
from common_funcs import CommonFuncs

logger = logging.getLogger()
logging.basicConfig(stream=sys.stdout, level=logging.INFO)

oauth_str: str = "oauth"
notifications_str: str = "notifications"

notifications_steps_client_names: list[str] = [aws.cloudwatch_str, aws.events_str, aws.lambda_str, aws.sns_str]
base_steps_client_names: list[str] = [aws.amplify_str, aws.cloudformation_str, aws.secretsmanager_str]

cf = CommonFuncs(
    logger,
    filename=str(os.path.basename(__file__)),
    json_paths=[(notifications_str, notifications_steps_client_names)] + base_steps_client_names,
)

amplify_ms_teams_notification_func_name: str = "AmplifyMsTeamsNotification"
bitbucket_account_name: str = "foobar-products-development"
bitbucket_url_this_file: str = (
    f"https://bitbucket.org/foobar-products-development/aws-scripts/src/main/aws-create/{cf.filename}"
)
custom_image_repo_name: str = "foobar/node"
custom_image_repo_uri: str = f"public.ecr.aws/q0o6a4s6/{custom_image_repo_name}"
filename_no_ext: str = cf.filename.rsplit(sep=".", maxsplit=1)[0]
filename_sh: str = f"{filename_no_ext}.sh"
filename_oauth_token_curl_cmd_txt: str = f"{filename_no_ext}-oauth-token-curl-cmd.txt"


def get_amplify_app_domain_name(repo: str, deploy_env: str, component: str, back_end_url: str, domain_name: str) -> str:
    repo_custom: str = ""
    custom_project_name: str = repo.rsplit(sep="-", maxsplit=1)[0]
    if "-" in custom_project_name:
        repo_custom = custom_project_name.split(sep="-", maxsplit=1)[1]
    if domain_name:
        if not validators.domain(domain_name):
            logger.error(f"## ERROR: Invalid domain name format: '{domain_name}')")
            return None
    return ".".join(
        [
            i
            for i in [
                component,
                deploy_env if deploy_env != cf.prod else None,
                repo_custom if repo_custom else None,
                domain_name if domain_name else ".".join(urlparse(back_end_url).netloc.split(".")[-2:]),
            ]
            if i
        ]
    )


def get_amplify_app_env_vars(
    secretsmanager, repo: str, back_end_url: str, tag: bool, is_internal: bool
) -> dict[str, str]:
    secret_name: str = (
        f"{('-'.join([i for n, i in enumerate(repo.split('-')) if n != 1]) if repo.count('-') > 1 else repo).lower()}/ENV_VARS"
    )

    logger.info(f"## Retrieving the secret: '{secret_name}'")
    try:
        secretsmanager_get_secret_value_res = secretsmanager.get_secret_value(SecretId=secret_name)
        logger.info("## Secrets Manager Get Secret Value successful response")
    except ClientError as ex:
        logger.error(
            f"## Secrets Manager Get Secret Value ERROR: '{ex}', in trying to retrieve the secret: '{secret_name}'"
        )
        return None

    back_end_url_placeholder: str = "<BE>"
    ex_placeholder: str = "<EXTERNAL>"
    in_placeholder: str = "<INTERNAL>"

    return {
        **({"DEPLOY_TAG": tag} if tag else {}),
        **{
            k: (
                v.split(sep=" ", maxsplit=1)[-1]
                if ex_in_
                else (v if v != back_end_url_placeholder and not k.endswith("GATEWAY_URL") else back_end_url)
            )
            for k, v in json.loads(secretsmanager_get_secret_value_res["SecretString"]).items()
            if (
                ex_in_ := (v.startswith(ex_placeholder) and not is_internal)
                or (v.startswith(in_placeholder) and is_internal)
            )
            or (not v.startswith(ex_placeholder) and not v.startswith(in_placeholder))
        },
    }


def get_amplify_app_tags(
    cdk_stack_tags: list[dict[str, str]], component: str, is_internal: bool
) -> list[dict[str, str]]:
    tags: list[dict[str, str]] = []
    key_str: str = "Key"
    value_str: str = "Value"
    for t in cdk_stack_tags:
        if t[key_str] == "component":
            t[value_str] = component.capitalize()
        tags.append(t)
    return tags


def get_back_end_url_and_cdk_stack_tags(
    cloudformation, cloudformation_res: dict[str, dict], repo: str, deploy_env: str, back_end_cdk_stack: str
) -> tuple[str, list[dict[str, str]]]:
    no_back_end_cdk_stack: bool = False
    if not back_end_cdk_stack:
        no_back_end_cdk_stack = True
        custom_project_name: str = repo.rsplit(sep="-", maxsplit=1)[0]
        custom_project_name = (
            "".join([i.capitalize() for i in custom_project_name.split(sep="-", maxsplit=1)])
            if "-" in custom_project_name
            else custom_project_name.capitalize()
        )
        if "-" in deploy_env:
            deploy_env_props: list[str] = deploy_env.rsplit(sep="-", maxsplit=1)
            if deploy_env_props[1] in {"demo", "preview"}:
                deploy_env = (
                    f"{deploy_env_props[0]}{deploy_env_props[1][0]}"
                    if deploy_env_props[0] == "sih"
                    else deploy_env_props[0]
                )
        back_end_cdk_stack: str = f"Cdk{custom_project_name}Gw{deploy_env.capitalize()}Stack"

    logger.info(f"## Retrieving back-end URL from the '{back_end_cdk_stack}' (AWS CDK) stack CloudFormation output")

    cloudformation_describe_stacks_str: str = "cloudformation_describe_stacks"
    try:
        cloudformation_res[cloudformation_describe_stacks_str] = cloudformation.describe_stacks(
            StackName=back_end_cdk_stack
        )
        logger.info("## CloudFormation Describe Stacks successful response")
    except ClientError as ex:
        logger.error(
            f"## CloudFormation Describe Stacks ERROR: '{ex}', in trying to retrieve the back-end URL "
            f"from the '{back_end_cdk_stack}' (AWS CDK) stack CloudFormation output (for repo: '{repo}')"
        )
        if no_back_end_cdk_stack:
            logger.error(
                "## Did you want to specify an optional back-end AWS CDK stack name ? See help info with '-h' option"
            )
        return None, None

    cdk_stack_meta: list[dict[str, str]] = cloudformation_res[cloudformation_describe_stacks_str]["Stacks"][0]
    cdk_stack_name_outputs: list[dict[str, str]] = cdk_stack_meta["Outputs"]
    back_end_url: str = None
    for i in cdk_stack_name_outputs:
        if (
            (output_key := i["OutputKey"])
            and output_key.startswith(f"{back_end_cdk_stack[: -(len('Stack'))].lower().capitalize()}url")
            and "private" not in output_key
        ):
            back_end_url = i["OutputValue"]
            break
    if back_end_url is None:
        logger.error(
            f"## CloudFormation Describe Stacks outputs: {cdk_stack_name_outputs} "
            f"(for '{back_end_cdk_stack}' (AWS CDK) stack)"
        )
        logger.error(
            f"## ERROR: Could not retrieve the back-end URL (from the '{back_end_cdk_stack}' (AWS CDK) stack "
            f"CloudFormation output)"
        )
        return None, None

    return back_end_url, cdk_stack_meta["Tags"]


def get_basic_auth_creds(
    secretsmanager, secretsmanager_res: dict[str, dict], amplify_app_name: str, secret_tags: list[dict[str, str]]
) -> str:
    logger.info("## Enable Basic Auth is set to: TRUE")

    logger.info("## Generating a password for Basic Auth")
    secret_exclude_chars: str = "@%*()_+=`~{}|[]\\:\";'?,./"  # Characters to exclude from generated secrets
    try:
        secretsmanager_get_random_password_res = secretsmanager.get_random_password(
            PasswordLength=32,
            ExcludeCharacters=secret_exclude_chars,
            ExcludeNumbers=False,
            ExcludePunctuation=True,
            ExcludeUppercase=False,
            ExcludeLowercase=False,
            IncludeSpace=False,
            RequireEachIncludedType=True,
        )
        logger.info("## Secrets Manager Get Random Password successful response")
    except ClientError as ex:
        logger.error(
            f"## Secrets Manager Get Random Password ERROR: '{ex}', in trying to generate a password for Basic Auth"
        )
        return None

    username_str: str = "username"
    password_str: str = "password"
    username: str = "foobar-admin"
    password: str = secretsmanager_get_random_password_res["RandomPassword"]

    secret_name: str = f"{amplify_app_name}/basic-auth-creds"
    logger.info(f"## Generating Basic Auth credentials, storing them in AWS Secrets Manager secret: '{secret_name}'")
    try:
        secretsmanager_res["secretsmanager_create_secret"] = secretsmanager.create_secret(
            Name=secret_name,
            Description=f"The AWS Amplify app Basic Auth credentials for `{amplify_app_name}`. Created using `{filename_sh}` shell script: {bitbucket_url_this_file}",
            SecretString=json.dumps({username_str: username, password_str: password}),
            Tags=secret_tags,
        )
        logger.info("## Secrets Manager Create Secret successful response")
    except ClientError as ex:
        logger.error(f"## Secrets Manager Create Secret ERROR: '{ex}', in trying to generate Basic Auth credentials")
        return None

    return base64.b64encode(f"{username}:{password}".encode("ascii")).decode("ascii")


def get_buildspec(repo: str, pwd: str, tag: str) -> str:
    project_name_meta: str = repo.rsplit(sep="-")
    path_meta: list[str] = [pwd, project_name_meta[0], project_name_meta[-1]]
    if tag is not None:
        path_meta.append("tag")
    path_meta.append("amplify.yml")
    with open(os.path.join(*path_meta), "r", encoding="utf-8") as f:
        return f.read()


def get_custom_http(repo: str, pwd: str) -> str:
    project_name_meta: str = repo.rsplit(sep="-")
    path_meta: list[str] = [pwd, project_name_meta[0], project_name_meta[-1], "customHttp.yml"]
    with open(os.path.join(*path_meta), "r", encoding="utf-8") as f:
        return f.read()


def get_custom_rules(domain_name: str, is_internal: bool) -> list[dict[str, str]]:
    rules: list[dict[str, str]] = []
    if not is_internal:
        urls: list[str] = [f"https://{i}{domain_name}" for i in ["www.", ""]]
        rules.append({"source": urls[0], "target": urls[1], "status": "301"})
    return rules + [
        {
            "source": "</^[^.]+$|\\.(?!(pdf|css|gif|ico|jpg|js|png|txt|svg|woff|woff2|ttf|map|json)$)([^.]+$)/>",
            "target": "/index.html",
            "status": "200",
        },
        {"source": "/<*>", "target": "/index.html", "status": "404-200"},
    ]


def oauth_steps(region: str) -> None:
    secretsmanager = cf.get_client(region, aws.secretsmanager_str)

    logger.info(f"## Generating the Bitbucket OAuth Token (for Bitbucket workspace: '{bitbucket_account_name}')")
    try:
        secretsmanager_get_secret_value_res = secretsmanager.get_secret_value(
            SecretId=f"bitbucket/{bitbucket_account_name}/oauth-consumer/amplify-app-create",
        )
        logger.info("## Secrets Manager Get Secret Value successful response")
    except ClientError as ex:
        logger.error(
            f"## Secrets Manager Get Secret Value ERROR: '{ex}', in trying to generate the Bitbucket OAuth Token"
        )
        sys.exit(1)

    oauth_consumer_auth = json.loads(secretsmanager_get_secret_value_res["SecretString"])
    oauth_consumer_auth_key = oauth_consumer_auth["Key"]
    oauth_consumer_auth_secret = oauth_consumer_auth["Secret"]

    url: str = "https://bitbucket.org/site/oauth2/access_token"
    payload: str = "grant_type=client_credentials"
    curl_cmd: str = f"curl -X POST -u '{oauth_consumer_auth_key}:{oauth_consumer_auth_secret}' {url} -d {payload}"

    with open(filename_oauth_token_curl_cmd_txt, "w+", encoding="utf-8") as f:
        f.write(curl_cmd.replace("'", '"'))


def notifications_steps(region: str, repo: str, deploy_env: str) -> None:
    amplify = cf.get_client(region, aws.amplify_str)

    clients, res = cf.get_clients_and_res_objs(region, notifications_steps_client_names)

    amplify_app_name: str = f"{repo}-{deploy_env}"

    if not cf.check_amplify_app_exists(amplify, amplify_app_name):
        logger.error(
            f"## ERROR: AWS Amplify app '{amplify_app_name}' doesn't exist! (in the '{region}' "
            f"['{cf.region_timezones_meta[region]}'] region)"
        )
        cf.write_to_json_paths(res, notifications_steps_client_names, json_paths_key=notifications_str)
        sys.exit(1)

    logger.info(f"## Adding AWS Amplify app '{amplify_app_name}' build pipeline notifications to MS Teams")

    amplify_app_id: str
    amplify_app_tags: dict[str, str]
    amplify_app_id, amplify_app_tags = cf.get_amplify_app_id_and_tags(amplify, amplify_app_name)
    amplify_app_tags_formatted: list[dict[str, str]] = [{"Key": k, "Value": v} for k, v in amplify_app_tags.items()]

    sns_list_topics_res_topics: list[dict] = cf.sns_list_topics(clients[aws.sns_str])

    logger.info(f"## Get the SNS topic ARN (for the AWS Amplify app ID: '{amplify_app_id}')")
    topic_arn: str = None
    for i in sns_list_topics_res_topics:
        if amplify_app_id in i["TopicArn"]:
            topic_arn = i["TopicArn"]
            break
    if topic_arn is None:
        logger.error(f"## ERROR: Could not find the SNS topic ARN (for the AWS Amplify app name: '{amplify_app_name}')")
        logger.error(
            "## Have you added at least 1x (Email) Notification already in AWS Amplify console ? "
            "This causes AWS Amplify to auto create a default SNS topic for the AWS Amplify app."
        )
        cf.write_to_json_paths(res, notifications_steps_client_names, json_paths_key=notifications_str)
        sys.exit(1)

    logger.info("## Adding AWS Amplify app tags to SNS topic")
    try:
        res[aws.sns_str]["sns_tag_resource"] = clients[aws.sns_str].tag_resource(
            ResourceArn=topic_arn,
            Tags=amplify_app_tags_formatted,
        )
        logger.info("## SNS Tag Resource successful response")
    except ClientError as ex:
        logger.error(f"## SNS Tag Resource ERROR: '{ex}'")
        cf.write_to_json_paths(res, notifications_steps_client_names, json_paths_key=notifications_str)
        sys.exit(1)

    logger.info(
        f"## Subscribe the '{amplify_ms_teams_notification_func_name}' Lambda function "
        f"to the AWS Amplify app '{amplify_app_name}' SNS topic: {topic_arn}"
    )
    try:
        amplify_ms_teams_notification_func_name_meta: dict = clients[aws.lambda_str].get_function(
            FunctionName=amplify_ms_teams_notification_func_name
        )
        logger.info("## Lambda Get Function successful response")
    except ClientError as ex:
        logger.error(f"## Lambda Get Function ERROR: '{ex}'")
        cf.write_to_json_paths(res, notifications_steps_client_names, json_paths_key=notifications_str)
        sys.exit(1)
    try:
        res[aws.sns_str]["sns_subscribe"] = clients[aws.sns_str].subscribe(
            TopicArn=topic_arn,
            Protocol="lambda",
            Endpoint=amplify_ms_teams_notification_func_name_meta["Configuration"]["FunctionArn"],
            ReturnSubscriptionArn=True,
        )
        logger.info("## SNS Subscribe successful response")
    except ClientError as ex:
        logger.error(
            f"## SNS Subscribe ERROR: '{ex}', will NOT add AWS Amplify app '{amplify_app_name}' "
            f"build pipeline notifications to MS Teams"
        )
        cf.write_to_json_paths(res, notifications_steps_client_names, json_paths_key=notifications_str)
        sys.exit(1)

    if not cf.is_deploy_env_internal(deploy_env):
        alarm_description: str = "HTTPS 5xx Errors"
        alarm_name: str = f"{amplify_app_name} - {alarm_description}"
        logger.info(f"## Adding a '{alarm_name}' CloudWatch alarm (for AWS Amplify app: '{amplify_app_name}')")
        try:
            res[aws.cloudwatch_str]["cloudwatch_put_metric_alarm"] = clients[aws.cloudwatch_str].put_metric_alarm(
                AlarmName=alarm_name,
                AlarmDescription=f"The AWS Amplify app CloudWatch alarm: `{alarm_description}`.",
                ActionsEnabled=True,
                AlarmActions=[topic_arn],
                MetricName="5xxErrors",
                Namespace="AWS/AmplifyHosting",
                Statistic="Sum",
                Dimensions=[{"Name": "App", "Value": amplify_app_id}],
                Period=60,
                EvaluationPeriods=1,
                DatapointsToAlarm=1,
                Threshold=1.0,
                ComparisonOperator="GreaterThanOrEqualToThreshold",
                TreatMissingData="notBreaching",
                Tags=amplify_app_tags_formatted,
            )
            logger.info("## CloudWatch Put Metric Alarm successful response")
        except ClientError as ex:
            logger.error(
                f"## CloudWatch Put Metric Alarm ERROR: '{ex}', in trying to add a '{alarm_name}' CloudWatch alarm "
                f"(for AWS Amplify app: '{amplify_app_name}')"
            )
            cf.write_to_json_paths(res, notifications_steps_client_names, json_paths_key=notifications_str)
            sys.exit(1)

    is_next_token = True
    next_token = None
    events_list_rules_res_rules: list = []
    while is_next_token:
        try:
            events_list_rules_res = clients[aws.events_str].list_rules(
                **{
                    k: v
                    for k, v in {
                        "NamePrefix": "amplify-",
                        "NextToken": next_token if next_token else None,
                    }.items()
                    if v
                }
            )
            logger.info("## EventBridge List Rules successful response")
        except ClientError as ex:
            logger.error(f"## EventBridge List Rules ERROR: '{ex}'")
            cf.write_to_json_paths(res, notifications_steps_client_names, json_paths_key=notifications_str)
            sys.exit(1)
        if "NextToken" in events_list_rules_res:
            next_token = events_list_rules_res["NextToken"]
        else:
            is_next_token = False
        events_list_rules_res_rules += events_list_rules_res["Rules"]

    logger.info("## Adding AWS Amplify app tags to EventBridge rule")
    try:
        res[aws.events_str]["events_tag_resource"] = clients[aws.events_str].tag_resource(
            ResourceARN=[i["Arn"] for i in events_list_rules_res_rules if amplify_app_id in i["Arn"]][0],
            Tags=amplify_app_tags_formatted,
        )
        logger.info("## EventBridge Tag Resource successful response")
    except ClientError as ex:
        logger.error(f"## EventBridge Tag Resource ERROR: '{ex}'")
        cf.write_to_json_paths(res, notifications_steps_client_names, json_paths_key=notifications_str)
        sys.exit(1)

    cf.write_to_json_paths(res, notifications_steps_client_names, json_paths_key=notifications_str)


def base_steps(
    region: str,
    repo: str,
    deploy_env: str,
    oauth_res: str,
    back_end_cdk_stack: str,
    custom_image_tag: str,
    domain_name: str,
    pwd: str,
    tag: str,
) -> None:
    repo = repo.lower()
    deploy_env = deploy_env.lower()
    component: str = repo.rsplit(sep="-", maxsplit=1)[-1]

    if "-" not in deploy_env and deploy_env not in cf.deploy_envs_default:
        logger.error(f"## ERROR: Invalid deploy env: '{deploy_env}' (for git repo: '{repo}')")
        logger.error("## Valid deploy envs:")
        logger.error(f"##   {cf.deploy_envs_default + [f'*-{i}' for i in [cf.preview, cf.demo]]}")
        logger.error("## Did you mean either:")
        logger.error(f"##   {[f'{deploy_env}-{i}' for i in [cf.preview, cf.demo]]} ?")
        sys.exit(1)

    if cf.is_deploy_env_non_git_tag(deploy_env):
        if tag:
            logger.error(f"## ERROR: Cannot specify a deployment git tag for '{deploy_env}' deploy env!")
            sys.exit(1)
    elif not tag:
        logger.error(f"## ERROR: Must specify a deployment git tag for '{deploy_env}' deploy env!")
        sys.exit(1)

    clients, res = cf.get_clients_and_res_objs(region, base_steps_client_names)

    amplify_app_name: str = f"{repo}-{deploy_env}"

    git_branch: str = (
        (
            cf.prod
            if deploy_env == cf.prod
            else ("main" if deploy_env != cf.dev and cf.dev not in deploy_env else "develop")
        )
        if "-" not in deploy_env or deploy_env.split(sep="-", maxsplit=1)[1] != cf.demo
        else cf.prod
    )
    logger.info(f"## Git branch: '{git_branch}' (for deploy env: '{deploy_env}')")

    if cf.check_amplify_app_exists(clients[aws.amplify_str], amplify_app_name):
        logger.error(
            f"## ERROR: AWS Amplify app '{amplify_app_name}' already exists! (in the '{region}' "
            f"['{cf.region_timezones_meta[region]}'] region)"
        )
        cf.write_to_json_paths(res, base_steps_client_names)
        sys.exit(1)

    back_end_url, cdk_stack_tags = get_back_end_url_and_cdk_stack_tags(
        clients[aws.cloudformation_str], res[aws.cloudformation_str], repo, deploy_env, back_end_cdk_stack
    )
    if back_end_url is None:
        cf.write_to_json_paths(res, base_steps_client_names)
        sys.exit(1)
    is_internal: bool = cf.is_deploy_env_internal(deploy_env)
    amplify_app_tags: list[dict[str, str]] = get_amplify_app_tags(cdk_stack_tags, component, is_internal)
    amplify_app_tags_simple: dict[str, str] = {t["Key"]: t["Value"] for t in amplify_app_tags}
    amplify_app_domain_name: str = get_amplify_app_domain_name(repo, deploy_env, component, back_end_url, domain_name)
    amplify_app_env_vars: dict[str, str] = get_amplify_app_env_vars(
        clients[aws.secretsmanager_str], repo, back_end_url, tag, is_internal
    )
    if any(i is None for i in [amplify_app_domain_name, amplify_app_env_vars]):
        cf.write_to_json_paths(res, base_steps_client_names)
        sys.exit(1)
    basic_auth_creds = None
    if is_internal:
        basic_auth_creds: str = get_basic_auth_creds(
            clients[aws.secretsmanager_str], res[aws.secretsmanager_str], amplify_app_name, amplify_app_tags
        )
        if basic_auth_creds is None:
            cf.write_to_json_paths(res, base_steps_client_names)
            sys.exit(1)
    custom_image_verified: bool = False
    if custom_image_tag:
        logger.info(f"## Checking for custom build image: '{custom_image_repo_uri}:{custom_image_tag}' ")
        try:
            ecr_public_list_apps_res = cf.get_client("us-east-1", aws.ecr_public_str).describe_image_tags(
                repositoryName=custom_image_repo_name,
            )
            logger.info("## ECR Public Describe Image Tags successful response")
        except ClientError as ex:
            logger.error(
                f"## ECR Public Describe Image Tags ERROR: '{ex}', in trying to create an AWS Amplify app: '{amplify_app_name}'"
            )
            cf.write_to_json_paths(res, base_steps_client_names)
            sys.exit(1)
        for i in ecr_public_list_apps_res["imageTagDetails"]:
            if i["imageTag"] == custom_image_tag:
                custom_image_digest: str = i["imageDetail"]["imageDigest"]
                logger.info(f"## Found custom build image: '{custom_image_digest}'")
                custom_image_verified = True
                break
    create_app_kwargs = {
        k: v
        for k, v in {
            "name": amplify_app_name,
            "description": f"The AWS Amplify app for `{amplify_app_name}`. Created using `{filename_sh}` shell script: {bitbucket_url_this_file}",
            "repository": f"https://bitbucket.org/{bitbucket_account_name}/{repo}",
            "platform": "WEB",
            "iamServiceRoleArn": None,  # TODO: (OPTIONAL) Add IAM service role for an AWS Amplify app, if needed.
            "oauthToken": json.loads(oauth_res)["access_token"],
            "environmentVariables": {
                **amplify_app_env_vars,
                **{
                    "_BUILD_TIMEOUT": "10",
                    "_CUSTOM_IMAGE": f"{custom_image_repo_uri}:{custom_image_tag if custom_image_verified else 'latest'}",
                },
            },
            "enableBranchAutoBuild": False,
            "enableBranchAutoDeletion": False,
            "enableBasicAuth": is_internal if is_internal else None,
            "basicAuthCredentials": basic_auth_creds,
            "customRules": get_custom_rules(amplify_app_domain_name, is_internal),
            "tags": amplify_app_tags_simple,
            "buildSpec": get_buildspec(repo, pwd, tag),
            "customHeaders": get_custom_http(repo, pwd),
            "enableAutoBranchCreation": False,
        }.items()
        if v is not None
    }
    logger.info("## Creating the AWS Amplify app")
    amplify_create_app_str: str = "amplify_create_app"
    try:
        res[aws.amplify_str][amplify_create_app_str] = clients[aws.amplify_str].create_app(**create_app_kwargs)
        logger.info("## Amplify Create App successful response")
    except ClientError as ex:
        logger.error(
            f"## Amplify Create App ERROR: '{ex}', in trying to create an AWS Amplify app: '{amplify_app_name}'"
        )
        cf.write_to_json_paths(res, base_steps_client_names)
        sys.exit(1)

    logger.info(f"## Getting the AWS Amplify app ID (for AWS Amplify app: '{amplify_app_name}')")
    amplify_app_id: str = (
        res[aws.amplify_str][amplify_create_app_str]["app"]["appId"]
        if amplify_create_app_str in res[aws.amplify_str] and res[aws.amplify_str][amplify_create_app_str]
        else None
    )
    if amplify_app_id is None:
        amplify_app_id = cf.get_amplify_app_id(clients[aws.amplify_str], amplify_app_name)

    logger.info(
        f"## Add a '{git_branch}' branch to the newly created AWS Amplify app (for AWS Amplify app: '{amplify_app_name}')"
    )
    create_branch_kwargs = {
        k: v
        for k, v in {
            "appId": amplify_app_id,
            "branchName": git_branch,
            "description": f"The AWS Amplify app `{git_branch}` branch for `{amplify_app_name}`. Created using `{filename_sh}` shell script: {bitbucket_url_this_file}",
            "stage": "PRODUCTION",
            "framework": "React",
            "enableNotification": False,
            "enableAutoBuild": cf.is_deploy_env_non_git_tag(deploy_env) if "unstable" not in deploy_env else False,
            # "environmentVariables": {},
            "basicAuthCredentials": basic_auth_creds,
            "enableBasicAuth": False,
            "enablePerformanceMode": bool(not is_internal),
            "tags": amplify_app_tags_simple,
            # "buildSpec": ,
            "ttl": "5",
            "displayName": git_branch,
            "enablePullRequestPreview": cf.is_deploy_env_non_git_tag(deploy_env),
            # "pullRequestEnvironmentName": ,
            # "backendEnvironmentArn": ,
        }.items()
        if v is not None
    }
    try:
        res[aws.amplify_str]["amplify_create_branch"] = clients[aws.amplify_str].create_branch(**create_branch_kwargs)
        logger.info("## Amplify Create Branch successful response")
    except ClientError as ex:
        logger.error(
            f"## Amplify Create Branch ERROR: '{ex}', in trying to create a new branch for "
            f"AWS Amplify app: '{amplify_app_name}'"
        )
        cf.write_to_json_paths(res, base_steps_client_names)
        sys.exit(1)

    logger.info(
        f"## Create a domain association for the AWS Amplify app: '{amplify_app_domain_name}' -> '{git_branch}' branch"
    )
    try:
        res[aws.amplify_str]["amplify_create_domain_association"] = clients[aws.amplify_str].create_domain_association(
            appId=amplify_app_id,
            domainName=amplify_app_domain_name,
            enableAutoSubDomain=False,
            subDomainSettings=[
                i
                for i in [
                    {"prefix": "", "branchName": git_branch},
                    {"prefix": "www", "branchName": git_branch} if not is_internal else None,
                ]
                if i
            ],
        )
        logger.info("## Amplify Create Domain Association successful response")
    except ClientError as ex:
        logger.error(
            f"## Amplify Create Domain Association ERROR: '{ex}', in trying to create a new domain association for "
            f"AWS Amplify app: '{amplify_app_name}'"
        )
        cf.write_to_json_paths(res, base_steps_client_names)
        sys.exit(1)

    logger.info(f"## Create a web-hook on AWS Amplify app '{git_branch}' branch")
    try:
        res[aws.amplify_str]["amplify_create_webhook"] = clients[aws.amplify_str].create_webhook(
            appId=amplify_app_id, branchName=git_branch, description=f"trigger{git_branch}"
        )
        logger.info("## Amplify Create Webhook successful response")
    except ClientError as ex:
        logger.error(
            f"## Amplify Create Webhook ERROR: '{ex}', in trying to create a new webhook for "
            f"AWS Amplify app: '{amplify_app_name}'"
        )
        cf.write_to_json_paths(res, base_steps_client_names)
        sys.exit(1)

    logger.info(f"## Releasing changes on AWS Amplify app '{git_branch}' branch build pipeline: '{amplify_app_name}'")
    try:
        res[aws.amplify_str]["amplify_start_job"] = clients[aws.amplify_str].start_job(
            appId=amplify_app_id,
            branchName=git_branch,
            # jobId=,  # Only required if 'jobType="RETRY"'
            jobType="RELEASE",
            jobReason=f"Releasing changes on AWS Amplify app `{git_branch}` branch build pipeline, using AWS Deploy Amplify shell script: "
            "https://bitbucket.org/foobar-products-development/aws-scripts/src/main/aws-deploy/aws-deploy-amplify.sh",
            commitId="HEAD",
            commitMessage="This is an autogenerated message",
            commitTime=datetime.now(timezone(cf.region_timezones_meta[region])),
        )
        logger.info("## Amplify Start Job successful response")
    except ClientError as ex:
        logger.error(
            f"## Amplify Start Job ERROR: '{ex}', will NOT deploy (release) "
            f"changes on AWS Amplify app build pipeline: '{amplify_app_name}'"
        )
        cf.write_to_json_paths(res, base_steps_client_names)
        sys.exit(1)

    cf.write_to_json_paths(res, base_steps_client_names)


def main(
    region: str,
    oauth: bool = False,
    notifications: bool = False,
    repo: str = None,
    deploy_env: str = None,
    oauth_res: str = None,
    back_end_cdk_stack: str = None,
    custom_image_tag: str = None,
    domain_name: str = None,
    pwd: str = None,
    tag: str = None,
):
    if oauth:
        cf.info_log_starting(opt=oauth_str)
        oauth_steps(region)
        cf.info_log_finished(opt=oauth_str)
    elif notifications:
        cf.info_log_starting(opt=notifications_str)
        notifications_steps(region, repo, deploy_env)
        cf.info_log_finished(opt=notifications_str)
    else:
        cf.info_log_starting()
        base_steps(region, repo, deploy_env, oauth_res, back_end_cdk_stack, custom_image_tag, domain_name, pwd, tag)
        cf.info_log_finished()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Create a new AWS Amplify app.")
    parser.add_argument(
        "--region",
        required=True,
        help="Specify the AWS region code, eg. '--region eu-west-2'.",
        type=str,
    )
    parser.add_argument(
        "--oauth",
        action="store_true",
        help="Specifies whether to get a Bitbucket OAuth token.",
    )
    parser.add_argument(
        "--notifications",
        action="store_true",
        help="Specifies whether to create an MS Teams notifications setup for an AWS Amplify app.",
    )
    parser.add_argument("--repo", help="Get the git repo name.", type=str)
    parser.add_argument(
        "--deploy_env",
        help="Specify whether to get the git repo branch name, for a given deployment environment.",
        type=str,
    )
    parser.add_argument(
        "--oauth_res", help="Specify the OAuth response, containing the Bitbucket OAuth token.", type=str
    )
    parser.add_argument(
        "--back_end_cdk_stack",
        help="Specify an optional back-end AWS CDK stack name, used to reference a back-end URL.",
        type=str,
    )
    parser.add_argument(
        "--custom_image_tag",
        help="Specify an optional custom image tag to use for the AWS Amplify app build settings custom image.",
        type=str,
    )
    parser.add_argument(
        "--domain_name",
        help="Specify an optional domain name to use for the front-end URL.",
        type=str,
    )
    parser.add_argument("--pwd", help="Specify the git repo path.", type=str)
    parser.add_argument("--tag", help="Specify the git tag.", type=str)
    args = parser.parse_args()
    main(
        region=args.region,
        oauth=args.oauth,
        notifications=args.notifications,
        repo=args.repo,
        deploy_env=args.deploy_env,
        oauth_res=args.oauth_res,
        back_end_cdk_stack=args.back_end_cdk_stack,
        custom_image_tag=args.custom_image_tag,
        domain_name=args.domain_name,
        pwd=args.pwd,
        tag=args.tag,
    )
