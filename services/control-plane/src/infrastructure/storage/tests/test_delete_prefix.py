from unittest.mock import Mock, call

import pytest

from infrastructure.storage import S3Storage


def test_delete_prefix_raises_for_partial_s3_success_and_can_retry():
    client = Mock()
    paginator = client.get_paginator.return_value
    paginator.paginate.side_effect = [
        [{"Contents": [{"Key": "project/first"}]}, {"Contents": [{"Key": "project/second"}, {"Key": "project/third"}]}],
        [{"Contents": [{"Key": "project/third"}]}],
    ]
    client.delete_objects.side_effect = [
        {"Deleted": [{"Key": "project/first"}]},
        {
            "ResponseMetadata": {"HTTPStatusCode": 200},
            "Deleted": [{"Key": "project/second"}],
            "Errors": [{"Key": "project/third", "Code": "AccessDenied", "Message": "Access Denied"}],
        },
        {"Deleted": [{"Key": "project/third"}]},
    ]
    storage = S3Storage(client=client, bucket="artifacts")

    with pytest.raises(RuntimeError, match=r"could not delete 1 of 2 objects \(AccessDenied\)"):
        storage.delete_prefix("project/")

    storage.delete_prefix("project/")
    assert paginator.paginate.call_args_list == [call(Bucket="artifacts", Prefix="project/")] * 2
    assert client.delete_objects.call_args_list == [
        call(Bucket="artifacts", Delete={"Objects": [{"Key": "project/first"}]}),
        call(Bucket="artifacts", Delete={"Objects": [{"Key": "project/second"}, {"Key": "project/third"}]}),
        call(Bucket="artifacts", Delete={"Objects": [{"Key": "project/third"}]}),
    ]


def test_delete_prefix_skips_empty_pages():
    client = Mock()
    client.get_paginator.return_value.paginate.return_value = [{}]

    S3Storage(client=client, bucket="artifacts").delete_prefix("empty/")

    client.delete_objects.assert_not_called()
