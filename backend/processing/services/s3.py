from pathlib import PurePosixPath

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.views.decorators.debug import sensitive_variables

from .credentials import decrypt_credentials


class S3Problem(Exception):
    def __init__(self, code, message, transient=False):
        self.code = code
        self.message = message
        self.transient = transient
        super().__init__(message)


def _translate_error(exc):
    if isinstance(exc, ClientError):
        code = str(exc.response.get('Error', {}).get('Code', ''))
        if code in {'SlowDown', 'Throttling', 'RequestTimeout', 'InternalError', 'ServiceUnavailable', '500', '503'}:
            return S3Problem('S3_TEMPORARY', 'S3 is temporarily unavailable. Please retry.', True)
        if code in {'InvalidAccessKeyId', 'SignatureDoesNotMatch', 'ExpiredToken', 'InvalidToken', 'InvalidSecurity'}:
            return S3Problem('S3_CREDENTIALS', 'AWS credentials are invalid or expired. Please reconnect.')
        if code in {'NoSuchBucket', '404', 'NotFound'}:
            return S3Problem('S3_NOT_FOUND', 'The bucket does not exist or cannot be accessed.')
        if code in {'AccessDenied', '403', 'Forbidden'}:
            return S3Problem('S3_ACCESS_DENIED', 'AWS denied access. Check credentials, bucket name and IAM permissions.')
        return S3Problem('S3_REQUEST_FAILED', 'S3 rejected the request. Check the bucket and region.')
    return S3Problem('S3_UNREACHABLE', 'Could not reach S3. Check the region and network connection.', True)


@sensitive_variables()
def make_client(connection):
    credentials = decrypt_credentials(connection)
    return boto3.client(
        's3', aws_access_key_id=credentials['access_key_id'],
        aws_secret_access_key=credentials['secret_access_key'],
        aws_session_token=credentials.get('session_token') or None,
        region_name=connection.region or None,
        config=Config(connect_timeout=5, read_timeout=10, retries={'max_attempts': 1, 'mode': 'standard'}),
    )


def check_bucket(connection):
    try:
        make_client(connection).head_bucket(Bucket=connection.bucket)
    except (ClientError, BotoCoreError) as exc:
        raise _translate_error(exc) from None


def list_files(connection, prefix='', cursor=''):
    request = {'Bucket': connection.bucket, 'Prefix': prefix, 'MaxKeys': 100}
    if cursor:
        request['ContinuationToken'] = cursor
    try:
        response = make_client(connection).list_objects_v2(**request)
    except (ClientError, BotoCoreError) as exc:
        raise _translate_error(exc) from None
    # The cursor follows S3 objects, including unsupported ones: an empty page can have a next page.
    files = [
        {'key': obj['Key'], 'size': obj['Size'], 'last_modified': obj['LastModified'].isoformat(),
         'format': PurePosixPath(obj['Key']).suffix.lower().lstrip('.')}
        for obj in response.get('Contents', [])
        if PurePosixPath(obj['Key']).suffix.lower() in {'.csv', '.xlsx', '.xls'}
    ]
    return {'files': files, 'next_cursor': response.get('NextContinuationToken'), 'bucket': connection.bucket}
