from unittest.mock import Mock

import pytest

from infrastructure.storage.s3 import S3Storage


@pytest.mark.parametrize("fail", [False, True])
def test_large_artifact_copy_is_conditional_and_aborts_partial_upload(fail):
    storage = object.__new__(S3Storage)
    storage.bucket = "test-bucket"
    storage.client = Mock()
    storage.client.create_multipart_upload.return_value = {"UploadId": "copy-upload"}
    storage.client.upload_part_copy.return_value = {"CopyPartResult": {"ETag": "part-etag"}}
    if fail:
        storage.client.upload_part_copy.side_effect = RuntimeError("Temporary storage failure")
    size = 5 * 1024**3 + 1

    def copy():
        return storage.copy("s3://test-bucket/source", "destination", checksum="sha256",
                            content_type="application/gzip", size_bytes=size, expected_etag='"source-etag"')

    if fail:
        with pytest.raises(RuntimeError):
            copy()
        storage.client.abort_multipart_upload.assert_called_once()
        storage.client.complete_multipart_upload.assert_not_called()
    else:
        assert copy().size_bytes == size
        calls = storage.client.upload_part_copy.call_args_list
        assert len(calls) == 41
        assert calls[0].kwargs["CopySourceRange"] == "bytes=0-134217727"
        assert calls[-1].kwargs["CopySourceRange"] == f"bytes={5 * 1024**3}-{size - 1}"
        assert all(call.kwargs["CopySourceIfMatch"] == '"source-etag"' for call in calls)
        storage.client.complete_multipart_upload.assert_called_once()
        storage.client.abort_multipart_upload.assert_not_called()
    storage.client.copy_object.assert_not_called()
