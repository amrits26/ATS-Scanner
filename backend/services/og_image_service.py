"""
Phase 3: OG Image Generation Service
Async ARQ job for LinkedIn-optimized share images with fallback
"""

import io
import asyncio
from typing import Optional
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from PIL import Image, ImageDraw, ImageFont
import httpx


# OG Image constants
OG_WIDTH = 1200
OG_HEIGHT = 630
FONT_SIZE_TITLE = 48
FONT_SIZE_TEXT = 32
FALLBACK_SCORE = 82  # Default if generation fails


class OGImageGenerator:
    """
    Generate LinkedIn-optimized OG images with score visualization
    Async-safe for ARQ job queue
    """
    
    def __init__(self, bucket_base_url: str = "https://storage.supabase.co/"):
        """
        Args:
            bucket_base_url: Supabase or S3 bucket base URL
        """
        self.bucket_base_url = bucket_base_url
        self.client = httpx.AsyncClient(timeout=10.0)
    
    async def upload_to_supabase(
        self,
        image_bytes: bytes,
        bucket_name: str,
        file_path: str
    ) -> str:
        """
        Upload generated image to Supabase Storage
        
        Args:
            image_bytes: PIL Image as bytes
            bucket_name: Supabase bucket name (e.g., 'og-images')
            file_path: Storage path (e.g., 'shares/{scan_id}.png')
        
        Returns:
            Public URL of uploaded image
        """
        try:
            # Upload to Supabase Storage via HTTP
            url = f"{self.bucket_base_url}storage/v1/object/public/{bucket_name}/{file_path}"
            
            headers = {
                # Typically passed via auth token
                "Content-Type": "image/png",
            }
            
            response = await self.client.post(
                url,
                content=image_bytes,
                headers=headers,
            )
            
            if response.status_code in (200, 201):
                return f"{self.bucket_base_url}storage/v1/object/public/{bucket_name}/{file_path}"
            else:
                raise Exception(f"Upload failed: {response.status_code}")
        
        except Exception as e:
            print(f"OG Image upload error: {e}")
            raise
    
    def generate_image_bytes(
        self,
        match_score: int,
        company_name: str = "Dream Company",
        job_title: str = "Your Next Role"
    ) -> bytes:
        """
        Generate OG image with score visualization
        
        Args:
            match_score: ATS match score (0-100)
            company_name: Company being matched
            job_title: Job title
        
        Returns:
            PNG image as bytes
        """
        # Create image with gradient background
        img = Image.new('RGB', (OG_WIDTH, OG_HEIGHT), color='#0A66C2')  # LinkedIn blue
        draw = ImageDraw.Draw(img)
        
        # Try to load a nicer font, fallback to default
        try:
            title_font = ImageFont.truetype("arial.ttf", FONT_SIZE_TITLE)
            text_font = ImageFont.truetype("arial.ttf", FONT_SIZE_TEXT)
        except:
            title_font = ImageFont.load_default()
            text_font = ImageFont.load_default()
        
        # Draw score circle (large, centered)
        circle_x = OG_WIDTH // 2
        circle_y = OG_HEIGHT // 3
        radius = 80
        
        # Score circle background
        draw.ellipse(
            [circle_x - radius, circle_y - radius, circle_x + radius, circle_y + radius],
            fill='#FFFFFF',
            outline='#0A66C2',
            width=4
        )
        
        # Score text
        score_color = '#00B050' if match_score >= 70 else '#FFC000' if match_score >= 50 else '#E7492E'
        draw.text(
            (circle_x, circle_y),
            f"{match_score}%",
            font=title_font,
            fill=score_color,
            anchor="mm"
        )
        
        # Title
        draw.text(
            (OG_WIDTH // 2, OG_HEIGHT // 2 + 50),
            "Your ATS Match Score",
            font=text_font,
            fill='#FFFFFF',
            anchor="mm"
        )
        
        # Subtitle
        draw.text(
            (OG_WIDTH // 2, OG_HEIGHT - 100),
            f"{company_name} • {job_title}",
            font=text_font,
            fill='#CCCCCC',
            anchor="mm"
        )
        
        # Brand
        draw.text(
            (OG_WIDTH // 2, OG_HEIGHT - 30),
            "IntelliResume AI — Optimize your resume for any job",
            font=text_font,
            fill='#FFFFFF',
            anchor="mm"
        )
        
        # Convert to bytes
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        return img_bytes.getvalue()
    
    async def generate_and_upload(
        self,
        scan_id: str,
        match_score: int,
        company_name: str,
        job_title: str,
        bucket_name: str = "og-images"
    ) -> str:
        """
        Generate OG image and upload to storage
        
        Args:
            scan_id: Analysis result ID (for filename)
            match_score: Score to display
            company_name: Company name
            job_title: Job title
            bucket_name: Storage bucket
        
        Returns:
            Public URL of uploaded image
        """
        try:
            # Generate image
            image_bytes = self.generate_image_bytes(
                match_score,
                company_name,
                job_title
            )
            
            # Upload to Supabase
            file_path = f"shares/{scan_id}.png"
            public_url = await self.upload_to_supabase(
                image_bytes,
                bucket_name,
                file_path
            )
            
            return public_url
        
        except Exception as e:
            print(f"OG generation failed: {e}")
            # Fallback: return generic OG image or placeholder
            return f"{self.bucket_base_url}storage/v1/object/public/{bucket_name}/fallback-og.png"


# ============================================================================
# ARQ Job: Generate OG image asynchronously
# ============================================================================

async def generate_og_image_job(
    db_session_factory,
    scan_id: str,
    match_score: int,
    company_name: str,
    job_title: str
) -> dict:
    """
    ARQ job handler for async OG image generation
    
    Args:
        db_session_factory: AsyncSessionLocal factory
        scan_id: Analysis result ID
        match_score: ATS score
        company_name: Company name
        job_title: Job title
    
    Returns:
        Job result with image URL
    """
    async with db_session_factory() as db:
        try:
            generator = OGImageGenerator()
            
            # Generate and upload image
            image_url = await generator.generate_and_upload(
                scan_id,
                match_score,
                company_name,
                job_title
            )
            
            # Update database
            stmt = text("""
                UPDATE og_image_generation
                SET status = 'completed', image_url = :image_url, completed_at = NOW()
                WHERE scan_id = :scan_id
            """)
            
            await db.execute(
                stmt,
                {"image_url": image_url, "scan_id": scan_id}
            )
            await db.commit()
            
            # Update analysis_results with og_image_url
            stmt_update_result = text("""
                UPDATE analysis_results
                SET og_image_url = :image_url
                WHERE id = :scan_id
            """)
            
            await db.execute(
                stmt_update_result,
                {"image_url": image_url, "scan_id": scan_id}
            )
            await db.commit()
            
            return {
                "success": True,
                "scan_id": scan_id,
                "image_url": image_url
            }
        
        except Exception as e:
            # Mark as failed, fallback to generic image
            stmt = text("""
                UPDATE og_image_generation
                SET status = 'failed', fallback_used = TRUE, completed_at = NOW(),
                    retry_count = retry_count + 1
                WHERE scan_id = :scan_id
            """)
            
            await db.execute(stmt, {"scan_id": scan_id})
            await db.commit()
            
            return {
                "success": False,
                "scan_id": scan_id,
                "error": str(e)
            }


async def retry_og_image_job(
    db_session_factory,
    scan_id: str,
    max_retries: int = 3
) -> dict:
    """
    Retry failed OG image generation
    
    Args:
        db_session_factory: AsyncSessionLocal factory
        scan_id: Analysis result ID
        max_retries: Maximum retry attempts
    
    Returns:
        Job result
    """
    async with db_session_factory() as db:
        # Check current retry count
        stmt = text("""
            SELECT retry_count, image_url FROM og_image_generation
            WHERE scan_id = :scan_id
        """)
        
        result = await db.execute(stmt, {"scan_id": scan_id})
        row = result.first()
        
        if not row or row[0] >= max_retries:
            return {"success": False, "scan_id": scan_id, "error": "Max retries exceeded"}
        
        # Retry generation
        try:
            generator = OGImageGenerator()
            
            # Fetch analysis data
            stmt_fetch = text("""
                SELECT score, job_title, company_name FROM analysis_results
                WHERE id = :scan_id
            """)
            
            fetch_result = await db.execute(stmt_fetch, {"scan_id": scan_id})
            analysis = fetch_result.first()
            
            if not analysis:
                raise Exception(f"Analysis {scan_id} not found")
            
            score, job_title, company_name = analysis
            
            # Generate new image
            image_url = await generator.generate_and_upload(
                scan_id,
                score,
                company_name or "Dream Company",
                job_title or "Your Next Role"
            )
            
            # Update
            stmt_update = text("""
                UPDATE og_image_generation
                SET image_url = :image_url, status = 'completed', completed_at = NOW()
                WHERE scan_id = :scan_id
            """)
            
            await db.execute(stmt_update, {"image_url": image_url, "scan_id": scan_id})
            await db.commit()
            
            return {"success": True, "scan_id": scan_id, "image_url": image_url}
        
        except Exception as e:
            return {"success": False, "scan_id": scan_id, "error": str(e)}
