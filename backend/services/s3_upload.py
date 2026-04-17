"""
s3_upload.py

Upload DOCX files to AWS S3 with 7-day signed URL expiration.

Usage:
    from backend.services.s3_upload import upload_resume_docx
    signed_url = await upload_resume_docx(docx_bytes, user_id, filename)
"""

import os
import logging
from datetime import timedelta
from typing import Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# AWS Configuration
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "ats-scanner-uploads")

# Initialize S3 client
s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
)


async def upload_resume_docx(
    docx_bytes: bytes,
    user_id: Optional[str] = None,
    filename: Optional[str] = None,
    expires_in_days: int = 7,
) -> str:
    """
    Upload DOCX file to S3 and return signed URL.
    
    **Args:**
    - docx_bytes: File content (bytes)
    - user_id: User ID for key generation (optional)
    - filename: Original filename (optional, defaults to resume.docx)
    - expires_in_days: URL expiration (default 7 days)
    
    **Returns:**
    str: S3 signed URL (valid for 7 days)
    
    **Example:**
    ```python
    url = await upload_resume_docx(docx_bytes, user_id="abc123", filename="resume_tailored.docx")
    # Returns: https://s3.amazonaws.com/ats-scanner-uploads/tailor-rewrites/abc123/1712700000_resume_tailored.docx?AWSAccessKeyId=...&Signature=...&Expires=...
    ```
    """
    
    try:
        from datetime import datetime
        import uuid
        
        # Generate S3 key
        timestamp = int(datetime.utcnow().timestamp())
        
        if user_id:
            s3_key = f"tailor-rewrites/{user_id}/{timestamp}_{filename or 'resume.docx'}"
        else:
            # Anonymous user
            s3_key = f"tailor-rewrites/anonymous/{timestamp}_{uuid.uuid4().hex[:8]}_{filename or 'resume.docx'}"
        
        # Upload to S3
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=s3_key,
            Body=docx_bytes,
            ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ServerSideEncryption="AES256",
            Metadata={
                "user_id": user_id or "anonymous",
                "uploaded_at": datetime.utcnow().isoformat(),
                "original_filename": filename or "resume.docx",
            },
        )
        
        # Generate signed URL (expires in N days)
        signed_url = s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": S3_BUCKET_NAME,
                "Key": s3_key,
            },
            ExpiresIn=int(expires_in_days * 24 * 3600),  # Convert days to seconds
        )
        
        logger.info(f"[S3] Uploaded DOCX to {s3_key} (signed URL valid for {expires_in_days} days)")
        return signed_url
        
    except ClientError as e:
        logger.error(f"[S3] Upload failed: {e}")
        raise Exception(f"S3 upload failed: {e.response['Error']['Message']}")
    except Exception as e:
        logger.error(f"[S3] Upload error: {e}")
        raise Exception(f"Upload error: {str(e)}")


async def delete_resume_docx(s3_key: str) -> bool:
    """
    Delete a DOCX file from S3 (for cleanup after download or expiration).
    """
    try:
        s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
        logger.info(f"[S3] Deleted {s3_key}")
        return True
    except ClientError as e:
        logger.error(f"[S3] Deletion failed: {e}")
        return False
