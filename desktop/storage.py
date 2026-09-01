"""AWEC storage sinks: local filesystem and optional Internet Archive S3.
No crawl payload is retained by this module unless a local sink is enabled.
"""
from __future__ import annotations
from pathlib import Path
import hashlib

class LocalSink:
    def __init__(self, root): self.root=Path(root)
    def put(self, domain, url, data):
        digest=hashlib.sha256(url.encode()).hexdigest()[:16]
        suffix=Path(url.split('?',1)[0]).suffix or '.bin'
        folder=self.root/domain; folder.mkdir(parents=True,exist_ok=True)
        p=folder/(digest+suffix); p.write_bytes(data); return str(p)

class InternetArchiveSink:
    def __init__(self, access_key, secret_key, endpoint_url, bucket):
        import boto3
        self.client=boto3.client('s3',aws_access_key_id=access_key,aws_secret_access_key=secret_key,endpoint_url=endpoint_url)
        self.bucket=bucket
    def put(self,key,data,content_type='application/octet-stream'):
        self.client.put_object(Bucket=self.bucket,Key=key,Body=data,ContentType=content_type)
        return key
