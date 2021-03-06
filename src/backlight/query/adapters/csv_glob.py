from boto3 import Session
from urllib.parse import urlparse
import fnmatch
import glob
import io
import pandas as pd
import warnings

from backlight.query.adapter import DataSourceAdapter
from backlight.query.adapters.csv import read_csv_and_set_index


class CSVGlobAdapter(DataSourceAdapter):
    """Data source adapter for csv files which is compatible with glob url
    """

    def __init__(self, url: str) -> None:
        """Initializer.

        Args:
            url     : Url to specify local file path. It shoule start with "file".
        """
        self._url = urlparse(url)
        assert self._url.scheme in ("file",)

    def query(
        self, symbol: pd.Timestamp, start_dt: pd.Timestamp, end_dt: str
    ) -> pd.DataFrame:
        paths = glob.glob(self._url.path)
        dfs = [read_csv_and_set_index(path) for path in paths if symbol in path]

        if len(dfs) == 0:
            return pd.DataFrame()

        df = pd.concat(dfs, axis=0).sort_index()
        df = df[(start_dt <= df.index) & (df.index <= end_dt)]
        return df


def _list_s3_keys(s3client: Session.client, bucket: str, prefix: str = "") -> list:
    response = s3client.list_objects(Bucket=bucket, Prefix=prefix)
    if "Contents" not in response:
        warnings.warn(
            "No contents in the response of "
            "s3client.list_objects(Bucket=bucket, Prefix=prefix)"
            "where bucket={}, prefix={}".format(bucket, prefix)
        )
        return []
    return [content["Key"] for content in response["Contents"]]


class S3CSVGlobAdapter(DataSourceAdapter):
    """Data source adapter for csv files on s3 which is compatible with
    glob url
    """

    _s3client = Session().client("s3")

    def __init__(self, url: str) -> None:
        """Initializer.

        Args:
            url     : Url to specify s3 file path. It shoule start with "s3".
        """
        self._url = urlparse(url)
        assert self._url.scheme in ("s3",)

    def query(
        self, symbol: str, start_dt: pd.Timestamp, end_dt: pd.Timestamp
    ) -> pd.DataFrame:
        """Query pandas dataframe.

        See also :class:`backlight.query.adapter`.
        """
        bucket = self._url.netloc
        key = self._url.path[1:]  # delete first '/'

        s3keys = _list_s3_keys(
            S3CSVGlobAdapter._s3client, bucket, prefix=key.split("*")[0]
        )

        objects = [
            S3CSVGlobAdapter._s3client.get_object(Bucket=bucket, Key=s3key)
            for s3key in s3keys
            if fnmatch.fnmatch(s3key, key) and symbol in s3key
        ]

        dfs = [
            read_csv_and_set_index(io.BytesIO(obj["Body"].read())) for obj in objects
        ]

        if len(dfs) == 0:
            return pd.DataFrame()

        df = pd.concat(dfs, axis=0).sort_index()
        df = df[(start_dt <= df.index) & (df.index <= end_dt)]
        return df
