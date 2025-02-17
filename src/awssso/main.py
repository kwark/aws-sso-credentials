#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from configparser import ConfigParser
from datetime import datetime, timedelta
from pathlib import Path

import boto3
import inquirer
from dateutil.parser import parse
from dateutil.tz import UTC, tzlocal

VERBOSE_MODE = False
DOCKER_CMD = ['docker', 'run', '--rm', '-t', '-v', f'{Path.home()}/.aws:/root/.aws', 'amazon/aws-cli']

AWS_CONFIG_PATH = f'{Path.home()}/.aws/config'
AWS_CREDENTIAL_PATH = f'{Path.home()}/.aws/credentials'
AWS_SSO_CACHE_PATH = f'{Path.home()}/.aws/sso/cache'
AWS_DEFAULT_REGION = 'eu-west-1'


class Colour:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def main():
    parser = argparse.ArgumentParser(description='Retrieves AWS credentials from SSO for use with CLI/Boto3 apps.')

    parser.add_argument('profile',
                        action='store',
                        nargs='?',
                        help='AWS config profile to retrieve credentials for.')

    parser.add_argument('--verbose', '-v',
                        action='store_true',
                        help='Show verbose output, messages, etc.')

    parser.add_argument('--use-default', '-d',
                        action='store_true',
                        help='Clones selected profile and credentials into the default profile.')

    parser.add_argument('--login',
                        action='store_true',
                        help='Perform an SSO login by default, not just when SSO credentials have expired')

    parser.add_argument('--docker',
                        action='store_true',
                        help='Use the docker version of the AWS CLI')

    args = parser.parse_args()

    # validate aws v2
    try:
        cmd = DOCKER_CMD if args.docker else ['aws']
        aws_version = subprocess.run(cmd + ['--version'], capture_output=True).stdout.decode('utf-8')

        if 'aws-cli/2' not in aws_version:
            _print_error('\n AWS CLI Version 2 not found. Please install. Exiting.')
            exit(1)

    except Exception as e:
        _print_error(
            f'\nAn error occured trying to find AWS CLI version. Do you have AWS CLI Version 2 installed?\n{e}')
        exit(1)

    global VERBOSE_MODE
    VERBOSE_MODE = args.verbose

    profile = _add_prefix(args.profile if args.profile else _select_profile())

    if args.login:
        _spawn_cli_for_auth(profile, args.docker)

    _set_profile_credentials(profile, args.profile, args.use_default if profile != 'default' else False)


def _set_profile_credentials(profile_section_name, profile_name, use_default=False):
    profile_opts = _get_aws_profile(profile_section_name)
    cache_login = _get_sso_cached_login(profile_opts)
    credentials = _get_sso_role_credentials(profile_opts, cache_login)

    if not use_default:
        _store_aws_credentials(profile_name, profile_opts, credentials)
    else:
        _store_aws_credentials('default', profile_opts, credentials)
        _copy_to_default_profile(profile_section_name)


def _get_aws_profile(profile_name):
    _print_msg(f'\nReading profile: [{profile_name}]')
    config = _read_config(AWS_CONFIG_PATH)
    profile_opts = config.items(profile_name)
    profile = dict(profile_opts)
    return profile


def _get_sso_cached_login(profile):
    _print_msg('\nChecking for SSO credentials...')

    cache = hashlib.sha1(profile["sso_start_url"].encode("utf-8")).hexdigest()
    sso_cache_file = f'{AWS_SSO_CACHE_PATH}/{cache}.json'

    if not Path(sso_cache_file).is_file():
        _print_error(
            'Current cached SSO login is invalid/missing. Login with the AWS CLI tool or use --login')

    else:
        data = _load_json(sso_cache_file)
        now = datetime.now().astimezone(UTC)
        expires_at = parse(data['expiresAt']).astimezone(UTC)

        if data.get('region') != profile['sso_region']:
            _print_error(
                'SSO authentication region in cache does not match region defined in profile')

        if now > expires_at:
            _print_error(
                'SSO credentials have expired. Please re-validate with the AWS CLI tool or --login option.')

        if (now + timedelta(minutes=15)) >= expires_at:
            _print_warn('Your current SSO credentials will expire in less than 15 minutes!')

        _print_success(f'Found credentials. Valid until {expires_at.astimezone(tzlocal())}')
        return data


def _get_sso_role_credentials(profile, login):
    _print_msg('\nFetching short-term CLI/Boto3 session token...')

    client = boto3.client('sso', region_name=profile['sso_region'])
    response = client.get_role_credentials(
        roleName=profile['sso_role_name'],
        accountId=profile['sso_account_id'],
        accessToken=login['accessToken'],
    )

    expires = datetime.utcfromtimestamp(response['roleCredentials']['expiration'] / 1000.0).astimezone(UTC)
    _print_success(f'Got session token. Valid until {expires.astimezone(tzlocal())}')

    return response["roleCredentials"]


def _store_aws_credentials(profile_name, profile_opts, credentials):
    _print_msg(f'\nAdding to credential files under [{profile_name}]')

    region = profile_opts.get("region", AWS_DEFAULT_REGION)
    config = _read_config(AWS_CREDENTIAL_PATH)

    if config.has_section(profile_name):
        config.remove_section(profile_name)

    config.add_section(profile_name)
    config.set(profile_name, "region", region)
    config.set(profile_name, "aws_access_key_id", credentials["accessKeyId"])
    config.set(profile_name, "aws_secret_access_key ", credentials["secretAccessKey"])
    config.set(profile_name, "aws_session_token", credentials["sessionToken"])

    _write_config(AWS_CREDENTIAL_PATH, config)


def _copy_to_default_profile(profile_name):
    _print_msg(f'Copying profile [{profile_name}] to [default]')

    config = _read_config(AWS_CONFIG_PATH)

    if config.has_section('default'):
        config.remove_section('default')

    config.add_section('default')

    for key, value in config.items(profile_name):
        config.set('default', key, value)

    _write_config(AWS_CONFIG_PATH, config)


def _select_profile():
    config = _read_config(AWS_CONFIG_PATH)

    profiles = []
    for section in config.sections():
        profiles.append(re.sub(r"^profile ", "", str(section)))
    profiles.sort()

    questions = [
        inquirer.List(
            'name',
            message='Please select an AWS config profile',
            choices=profiles
        ),
    ]
    answer = inquirer.prompt(questions)
    return answer['name'] if answer else sys.exit(1)


def _spawn_cli_for_auth(profile, docker=False):
    cmd = DOCKER_CMD if docker else ['aws']
    subprocess.run(cmd + ['sso', 'login', '--profile', re.sub(r"^profile ", "", str(profile))],
                   stderr=sys.stderr,
                   stdout=sys.stdout,
                   check=True)


def _print_colour(colour, message, always=False):
    if always or VERBOSE_MODE:
        if os.environ.get('CLI_NO_COLOR', False):
            print(message)
        else:
            print(''.join([colour, message, Colour.ENDC]))


def _print_error(message):
    _print_colour(Colour.FAIL, message, always=True)
    sys.exit(1)


def _print_warn(message):
    _print_colour(Colour.WARNING, message, always=True)


def _print_msg(message):
    _print_colour(Colour.OKBLUE, message)


def _print_success(message):
    _print_colour(Colour.OKGREEN, message)


def _add_prefix(name):
    return f'profile {name}' if name != 'default' else 'default'


def _read_config(path):
    config = ConfigParser()
    config.read(path)
    return config


def _write_config(path, config):
    with open(path, "w") as destination:
        config.write(destination)


def _load_json(path):
    try:
        with open(path) as context:
            return json.load(context)
    except ValueError:
        pass  # skip invalid json


if __name__ == "__main__":
    main()
