import csv
import json
import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pymysql

sys.path.append(os.path.dirname(os.getcwd()))

# pylint: disable=wrong-import-position
from aws_service_name import AwsServiceName as aws
from common_funcs import CommonFuncs

logger = logging.getLogger()
logging.basicConfig(stream=sys.stdout, level=logging.INFO)

base_steps_client_names: list[str] = [aws.secretsmanager_str]

cf = CommonFuncs(
    logger,
    filename=str(os.path.basename(__file__)),
    json_paths=base_steps_client_names,
)

sep: str = "_"
databases_str: str = "databases"
databases_path: str = os.path.join(os.getcwd(), databases_str)

default_host: str = "127.0.0.1"
default_port: str = "3306"


def execute_mysql_command(cur, description, command):
    cur.execute(command)
    logger.info(f"## SQL {description} command: {command}")


def main(
    region: str,
    db_schema: str,
    secret: str,
    host: str = None,
    port: str = None,
):
    cf.info_log_starting()

    Path(databases_path).mkdir(exist_ok=True)

    if host is None:
        logger.info(f"## Default 'host' to: {default_host}")
        host = default_host
    if port is None:
        logger.info(f"## Default 'port' to: {default_port}")
        port = default_port

    secretsmanager_res = cf.get_client(region, aws.secretsmanager_str).get_secret_value(SecretId=secret)
    secretsmanager_res_obs = {k: v if k != "SecretString" else "****" for k, v in dict(secretsmanager_res).items()}
    logger.info(f"## Secrets Manager Get Secret Value response: {secretsmanager_res_obs}")
    admin_secret = json.loads(secretsmanager_res["SecretString"])
    try:
        mysql_cnx = pymysql.connect(
            user=admin_secret["username"],
            password=admin_secret["password"],
            host=host,
            port=int(port),
        )
        logger.info("## Connection to RDS MySQL instance succeeded.")
    except pymysql.MySQLError as e:
        logger.error(f"## Unexpected error: Could not connect to MySQL instance: {e}")
        sys.exit(1)

    with mysql_cnx.cursor() as cur:
        execute_mysql_command(cur, "Use DB schema", f"USE `{db_schema}`;")

        databases_db_schema_path: str = os.path.join(
            databases_path, sep.join([datetime.today().strftime("%Y%m%d"), db_schema])
        )
        if os.path.exists(databases_db_schema_path):
            shutil.rmtree(databases_db_schema_path)
        Path(databases_db_schema_path).mkdir()

        execute_mysql_command(cur, f"Show tables in the '{db_schema}' database", "SHOW TABLES;")
        for n, r in enumerate([i[0] for i in cur.fetchall()]):
            execute_mysql_command(cur, f"({n + 1}) Get all rows from '{r}' table", f"SELECT * FROM `{r}`;")
            with open(
                os.path.join(databases_db_schema_path, f"{r}.csv"), "w+", encoding="utf-8", newline=""
            ) as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([col[0] for col in cur.description])  # Add column headers
                writer.writerows(cur.fetchall())

    cf.info_log_finished()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=f"For a specific database (DB), on an RDS instance, backup all DB tables to CSV files - "
        f"one CSV file per DB table (see outputs in: '{databases_path}')."
    )
    parser.add_argument(
        "--region",
        required=True,
        help="Specify the AWS region code, eg. '--region eu-west-2'.",
        type=str,
    )
    parser.add_argument(
        "--db_schema",
        required=True,
        help="Specify the RDS instance database name, eg. '--db_schema dog_gw_staging'.",
        type=str,
    )
    parser.add_argument(
        "--secret",
        required=True,
        help="Specify the ARN of the AWS Secrets Manager secret, containing the RDS instance user credentials, "
        "eg. '--secret arn:aws:secretsmanager:*:*:secret:DogDatabaseDevStaging/rds-mysql-admin-*'.",
        type=str,
    )
    parser.add_argument(
        "--host",
        help=f"(Optional) Defaults to localhost. Specify the host for connecting to the RDS instance, eg. '--host {default_host}'.",
        type=str,
    )
    parser.add_argument(
        "--port",
        help=f"(Optional) Defaults to '{default_port}'. Specify the port for connecting to the RDS instance, eg. '--port 9999'.",
        type=str,
    )
    args = parser.parse_args()
    main(
        region=args.region,
        db_schema=args.db_schema,
        secret=args.secret,
        host=args.host,
        port=args.port,
    )
