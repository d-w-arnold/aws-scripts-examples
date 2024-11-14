import logging
import os
import sys
from collections import defaultdict
from itertools import chain
from operator import methodcaller

from botocore.exceptions import ClientError
from tld import get_tld

sys.path.append(os.path.dirname(os.getcwd()))

# pylint: disable=wrong-import-position
from aws_service_name import AwsServiceName as aws
from common_funcs import CommonFuncs

logger = logging.getLogger()
logging.basicConfig(stream=sys.stdout, level=logging.INFO)

base_steps_client_names: list[str] = [aws.route53_str]

cf = CommonFuncs(
    logger,
    filename=str(os.path.basename(__file__)),
    json_paths=base_steps_client_names,
)

domain_name_aws_valid: str = "acm-validations.aws."

comp_portal: str = "portal"

key_name: str = "Name"
key_type: str = "Type"
key_value: str = "Value"

record_change_action: str = "DELETE"
record_type: str = "CNAME"


def main(region: str):
    cf.info_log_starting()

    acm = cf.get_client(region, aws.acm_str)

    clients, res = cf.get_clients_and_res_objs(region, base_steps_client_names)

    is_next_token: bool = True
    next_token: str = None
    route53_hosted_zones_meta: list[dict] = []
    while is_next_token:
        try:
            route53_list_hosted_zones_res = clients[aws.route53_str].list_hosted_zones(
                **{
                    k: v
                    for k, v in {
                        "Marker": next_token if next_token else None,
                    }.items()
                    if v
                }
            )
            logger.info("## Route53 List Hosted Zones successful response")
        except ClientError as ex:
            logger.error(f"## Route53 List Hosted Zones ERROR: '{ex}'")
            cf.write_to_json_paths(res, base_steps_client_names)
            sys.exit(1)
        route53_hosted_zones_meta += route53_list_hosted_zones_res["HostedZones"]
        if route53_list_hosted_zones_res.get("IsTruncated") and "NextMarker" in route53_list_hosted_zones_res:
            next_token = route53_list_hosted_zones_res["NextMarker"]
        else:
            is_next_token = False

    route53_hosted_zones_name_id: dict[str, str] = {}
    route53_list_resource_record_sets_map: dict[str, list[dict]] = {}
    for route53_hosted_zone_meta in route53_hosted_zones_meta:
        if not route53_hosted_zone_meta["Config"]["PrivateZone"]:
            route53_hosted_zones_name_id[route53_hosted_zone_meta[key_name]] = route53_hosted_zone_meta["Id"]
            is_next_token = True
            next_token = None
            route53_list_resource_record_sets_list: list[dict] = []
            while is_next_token:
                try:
                    route53_list_resource_record_sets_res = clients[aws.route53_str].list_resource_record_sets(
                        HostedZoneId=route53_hosted_zones_name_id[route53_hosted_zone_meta[key_name]],
                        **{
                            k: v
                            for k, v in {
                                "StartRecordName": next_token if next_token else None,
                            }.items()
                            if v
                        },
                    )
                    logger.info("## Route53 List Hosted Zones successful response")
                except ClientError as ex:
                    logger.error(f"## Route53 List Hosted Zones ERROR: '{ex}'")
                    cf.write_to_json_paths(res, base_steps_client_names)
                    sys.exit(1)
                route53_list_resource_record_sets_list += [
                    i
                    for i in route53_list_resource_record_sets_res["ResourceRecordSets"]
                    if i[key_type] == record_type
                    and (value := str(i["ResourceRecords"][0][key_value]))
                    and value.endswith(domain_name_aws_valid)
                ]
                if (
                    route53_list_resource_record_sets_res.get("IsTruncated")
                    and "NextRecordName" in route53_list_resource_record_sets_res
                ):
                    next_token = route53_list_resource_record_sets_res["NextRecordName"]
                else:
                    is_next_token = False
            if route53_list_resource_record_sets_list:
                route53_list_resource_record_sets_map[route53_hosted_zone_meta[key_name]] = (
                    route53_list_resource_record_sets_list
                )

    route53_list_resource_record_sets_map_acm: dict[str, list[dict]] = dict(route53_list_resource_record_sets_map)
    route53_list_resource_record_sets_map_amplify: dict[str, list[dict]] = dict(route53_list_resource_record_sets_map)

    is_next_token = True
    next_token = None
    acm_certificates_meta: list[dict] = []
    while is_next_token:
        try:
            acm_list_certificates_res = acm.list_certificates(
                **{
                    k: v
                    for k, v in {
                        "NextToken": next_token if next_token else None,
                    }.items()
                    if v
                }
            )
            logger.info("## ACM List Certificates successful response")
        except ClientError as ex:
            logger.error(f"## ACM List Certificates ERROR: '{ex}'")
            cf.write_to_json_paths(res, base_steps_client_names)
            sys.exit(1)
        for certificate_arn in [i["CertificateArn"] for i in acm_list_certificates_res["CertificateSummaryList"]]:
            try:
                acm_describe_certificate_res = acm.describe_certificate(
                    CertificateArn=certificate_arn,
                )
                logger.info(f"## ACM Describe Certificate successful response: '{certificate_arn}'")
            except ClientError as ex:
                logger.error(f"## ACM Describe Certificate ERROR: '{ex}'")
                cf.write_to_json_paths(res, base_steps_client_names)
                sys.exit(1)
            acm_certificates_meta.append(acm_describe_certificate_res["Certificate"])
        if "NextToken" in acm_list_certificates_res:
            next_token = acm_list_certificates_res["NextToken"]
        else:
            is_next_token = False

    for acm_certificate_meta in acm_certificates_meta:
        url: str = f"https://{acm_certificate_meta['DomainName']}"
        route53_resource_record_sets_key: str = f"{get_tld(url, as_object=True).fld}."
        if (
            route53_resource_record_sets := route53_list_resource_record_sets_map_acm.get(
                route53_resource_record_sets_key
            )
        ) and (
            acm_certificate_resource_record_names := {
                i["ResourceRecord"][key_name] for i in acm_certificate_meta["DomainValidationOptions"]
            }
        ):
            route53_list_resource_record_sets_map_acm[route53_resource_record_sets_key] = [
                route53_resource_record_set
                for route53_resource_record_set in route53_resource_record_sets
                if (name := route53_resource_record_set[key_name])
                and comp_portal not in name
                and name not in acm_certificate_resource_record_names
            ]

    route53_list_resource_record_sets_map_acm = {
        k: v for k, v in route53_list_resource_record_sets_map_acm.items() if v
    }

    amplify_certificates_meta: list[tuple[str, dict]] = []
    amplify_cert_meta_keys: list[str] = [key_name, key_type, key_value]
    for r, _ in cf.region_timezones_meta.items():
        amplify = cf.get_client(r, aws.amplify_str)
        for amplify_app in cf.amplify_list_apps(amplify):
            amplify_app_name: str = amplify_app["name"]
            try:
                amplify_list_domain_associations_res = amplify.list_domain_associations(appId=amplify_app["appId"])
                logger.info(f"## Amplify List Domain Associations successful response: '{amplify_app_name}'")
            except ClientError as ex:
                logger.error(f"## Amplify List Domain Associations ERROR: '{ex}'")
                cf.write_to_json_paths(res, base_steps_client_names)
                sys.exit(1)
            amplify_certificates_meta += [
                (
                    f"{get_tld(url, as_object=True).fld}.",
                    {
                        amplify_cert_meta_keys[n]: amplify_cert_meta_item
                        for n, amplify_cert_meta_item in enumerate(i["certificateVerificationDNSRecord"].split(sep=" "))
                    },
                )
                for i in amplify_list_domain_associations_res["domainAssociations"]
                if (url := f"https://{i['domainName']}")
            ]

    amplify_certificates_meta_map: dict[str, set[str]] = {}
    for k, v in amplify_certificates_meta:
        if k not in amplify_certificates_meta_map:
            amplify_certificates_meta_map[k] = set()
        new_meta = amplify_certificates_meta_map[k]
        new_meta.add(v[key_name])
        amplify_certificates_meta_map[k] = new_meta

    route53_resource_record_sets_keys_found = set()
    for (
        route53_resource_record_sets_key,
        amplify_certificate_resource_record_names,
    ) in amplify_certificates_meta_map.items():
        route53_resource_record_sets_keys_found.add(route53_resource_record_sets_key)
        if route53_resource_record_sets := route53_list_resource_record_sets_map_amplify.get(
            route53_resource_record_sets_key
        ):
            route53_list_resource_record_sets_map_amplify[route53_resource_record_sets_key] = [
                route53_resource_record_set
                for route53_resource_record_set in route53_resource_record_sets
                if (name := route53_resource_record_set[key_name])
                and comp_portal in name
                and name not in amplify_certificate_resource_record_names
            ]

    route53_list_resource_record_sets_map_amplify = {
        k: v
        for k, v in route53_list_resource_record_sets_map_amplify.items()
        if v and k in route53_resource_record_sets_keys_found
    }

    route53_list_resource_record_sets_map_all = (
        route53_list_resource_record_sets_map_acm,
        route53_list_resource_record_sets_map_amplify,
    )
    if any(k for k in route53_list_resource_record_sets_map_all):
        route53_list_resource_record_sets_dd: defaultdict = defaultdict(list)
        for k, v in chain.from_iterable(map(methodcaller("items"), route53_list_resource_record_sets_map_all)):
            route53_list_resource_record_sets_dd[k].extend(v)

        res[aws.route53_str]["change_resource_record_sets"] = {}
        for k, v in route53_list_resource_record_sets_dd.items():
            if v:
                route53_hosted_zone_id: str = route53_hosted_zones_name_id[k]
                changes: list = [{"Action": record_change_action, "ResourceRecordSet": meta} for meta in v]
                try:
                    res[aws.route53_str]["change_resource_record_sets"][k] = clients[
                        aws.route53_str
                    ].change_resource_record_sets(
                        HostedZoneId=route53_hosted_zone_id,
                        ChangeBatch={
                            "Comment": f"Change batch request (from: '{cf.filename}' script) to '{record_change_action}' "
                            f"({len(changes)}x) '{record_type}' type records (for domain: '{k}') in "
                            f"hosted zone: {route53_hosted_zone_id}",
                            "Changes": changes,
                        },
                    )
                    logger.info(
                        f"## Route53 Change Resource Record Sets ({record_change_action}) successful response: '{k}'"
                    )
                except ClientError as ex:
                    logger.error(f"## Route53 Change Resource Record Sets ERROR: '{ex}'")
                    cf.write_to_json_paths(res, base_steps_client_names)
                    sys.exit(1)
    else:
        logger.info(f"## No AWS Route53 DNS ('{record_type}') records to clean-up.")

    cf.write_to_json_paths(res, base_steps_client_names)

    cf.info_log_finished()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=f"Clean-up AWS Route53 DNS ('{record_type}') records, "
        f"specifically '{domain_name_aws_valid}' records, which are no longer in "
        f"use by: Amazon Certificate Manager (ACM), AWS Amplify, etc."
    )
    # parser.add_argument(
    #     "--region",
    #     required=True,
    #     help="Specify the AWS region code, eg. '--region eu-west-2'.",
    #     type=str,
    # )
    args = parser.parse_args()
    main(region="us-east-1")
