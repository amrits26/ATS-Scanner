"""
Phase 3: SSR Share Route with OG Meta Tags
GET /share/{scan_id} - Server-side rendered HTML with LinkedIn meta tags
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime

from backend.database import get_db
from backend.services.referral_service import ReferralShareService

router = APIRouter(tags=["Phase 3 Growth Engine"])

# Referral service (for discount codes)
referral_service = ReferralShareService(api_key=None)  # No stripe key needed for reads


# ============================================================================
# GET /share/{share_token} - SSR Share Landing Page
# ============================================================================

@router.get("/share/{share_token}", response_class=HTMLResponse)
async def share_landing_page(
    share_token: str,
    db: AsyncSession = Depends(get_db),
    request: Request = None
):
    """
    Server-side rendered share landing page
    
    Injects OG meta tags for LinkedIn scraper:
    - og:title - Match score headline
    - og:description - Job title match
    - og:image - Pillow-generated scorecard
    - og:url - Canonical URL with cache buster (?v=timestamp)
    
    This route is designed to be scraped by LinkedIn's crawler.
    
    URL: https://intelliresume.ai/share/{share_token}
    """
    
    try:
        # Get share details from database
        stmt = text("""
            SELECT 
                rs.id,
                rs.referrer_email,
                rs.views_count,
                ar.score,
                ar.company_name,
                ar.job_title,
                ar.og_image_url,
                rd.discount_code,
                rd.valid_until,
                ar.created_at
            FROM referral_shares rs
            JOIN analysis_results ar ON rs.referrer_scan_id = ar.id
            LEFT JOIN referral_discounts rd ON rs.id = rd.share_id
            WHERE rs.share_token = :token
            LIMIT 1
        """)
        
        result = await db.execute(stmt, {"token": share_token})
        row = result.first()
        
        if not row:
            return _render_404()
        
        (share_id, referrer_email, views_count, score, company_name, 
         job_title, og_image_url, discount_code, valid_until, created_at) = row
        
        # Increment view count (don't wait for DB)
        try:
            stmt_view = text("""
                UPDATE referral_shares
                SET views_count = views_count + 1, last_view_at = NOW()
                WHERE id = :share_id
            """)
            await db.execute(stmt_view, {"share_id": share_id})
            # Don't commit here, let async task handle it
        except:
            pass  # View count is non-critical
        
        # Extract data
        company_name = company_name or "Your Dream Company"
        job_title = job_title or "Your Next Role"
        discount_percent = 20
        
        # Build canonical URL with cache buster
        # Cache buster: ?v={timestamp} prevents LinkedIn from caching old image
        cache_buster = int(created_at.timestamp()) if created_at else int(datetime.utcnow().timestamp())
        canonical_url = f"https://intelliresume.ai/share/{share_token}?v={cache_buster}"
        
        # OG image URL with cache buster
        og_image_with_buster = f"{og_image_url}?v={cache_buster}" if og_image_url else "https://intelliresume.ai/og-default.png"
        
        # Build OG description with discount hook
        discount_text = f" Get {discount_percent}% off Pro!" if discount_code else ""
        og_description = f"My ATS Match Score for {job_title} at {company_name}: {score}%{discount_text}"
        
        # Build HTML with OG meta tags
        html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{score}% ATS Match Score for {job_title}</title>
            
            <!-- OG Meta Tags (LinkedIn, Twitter, Facebook) -->
            <meta property="og:type" content="website">
            <meta property="og:url" content="{canonical_url}">
            <meta property="og:title" content="{score}% Match for {job_title} at {company_name}">
            <meta property="og:description" content="{og_description}">
            <meta property="og:image" content="{og_image_with_buster}">
            <meta property="og:image:type" content="image/png">
            <meta property="og:image:width" content="1200">
            <meta property="og:image:height" content="630">
            
            <!-- Twitter Card -->
            <meta name="twitter:card" content="summary_large_image">
            <meta name="twitter:title" content="{score}% ATS Match Score">
            <meta name="twitter:description" content="{og_description}">
            <meta name="twitter:image" content="{og_image_with_buster}">
            
            <!-- App Meta -->
            <meta name="description" content="IntelliResume AI - Get your ATS match score and optimize your resume">
            <meta name="theme-color" content="#0A66C2">
            <link rel="canonical" href="{canonical_url}">
            
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                    background: linear-gradient(135deg, #0A66C2 0%, #0B5594 100%);
                    margin: 0;
                    padding: 20px;
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }}
                
                .container {{
                    background: white;
                    border-radius: 12px;
                    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.1);
                    max-width: 600px;
                    width: 100%;
                    overflow: hidden;
                }}
                
                .header {{
                    background: linear-gradient(135deg, #0A66C2 0%, #0B5594 100%);
                    padding: 40px 20px;
                    text-align: center;
                    color: white;
                }}
                
                .score-circle {{
                    width: 120px;
                    height: 120px;
                    border-radius: 50%;
                    background: white;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0 auto 20px;
                    font-size: 48px;
                    font-weight: bold;
                    color: {self._score_color(score)};
                }}
                
                .header h1 {{
                    margin: 0 0 10px 0;
                    font-size: 28px;
                    font-weight: 700;
                }}
                
                .header p {{
                    margin: 0;
                    font-size: 16px;
                    opacity: 0.9;
                }}
                
                .content {{
                    padding: 40px 20px;
                    text-align: center;
                }}
                
                .job-info {{
                    margin: 20px 0;
                    font-size: 16px;
                    color: #333;
                }}
                
                .job-info strong {{
                    color: #0A66C2;
                }}
                
                .cta-section {{
                    margin-top: 30px;
                    padding: 20px;
                    background: #f5f5f5;
                    border-radius: 8px;
                }}
                
                .cta-button {{
                    display: inline-block;
                    background: #0A66C2;
                    color: white;
                    padding: 12px 30px;
                    border-radius: 6px;
                    text-decoration: none;
                    font-weight: 600;
                    margin-top: 15px;
                    transition: all 0.3s ease;
                }}
                
                .cta-button:hover {{
                    background: #0B5594;
                    transform: translateY(-2px);
                    box-shadow: 0 4px 12px rgba(10, 102, 194, 0.3);
                }}
                
                .discount {{
                    background: #FFF4E6;
                    border-left: 4px solid #FF9800;
                    padding: 15px;
                    margin: 20px 0;
                    border-radius: 4px;
                    color: #333;
                    font-weight: 600;
                }}
                
                .discount-code {{
                    background: white;
                    padding: 8px 12px;
                    border-radius: 4px;
                    font-family: 'Courier New', monospace;
                    font-weight: 700;
                    color: #0A66C2;
                    display: inline-block;
                    margin: 10px 0;
                    cursor: pointer;
                    border: 2px dashed #FF9800;
                }}
                
                .referrer-note {{
                    font-size: 14px;
                    color: #666;
                    margin-top: 20px;
                    padding-top: 20px;
                    border-top: 1px solid #eee;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="score-circle">{score}%</div>
                    <h1>Your ATS Match Score</h1>
                    <p>{job_title} @ {company_name}</p>
                </div>
                
                <div class="content">
                    <div class="job-info">
                        <strong>Position:</strong> {job_title}<br>
                        <strong>Company:</strong> {company_name}<br>
                        <strong>Match Score:</strong> {score}%
                    </div>
                    
                    {self._render_discount_section(discount_code, discount_percent, valid_until)}
                    
                    <div class="cta-section">
                        <h3>Upgrade to Pro</h3>
                        <p>Get full optimization + unlimited scans</p>
                        <a href="https://intelliresume.ai/pricing?promo={discount_code}" class="cta-button">
                            Upgrade Now {discount_percent}% OFF
                        </a>
                    </div>
                    
                    <div class="referrer-note">
                        Shared by a fellow job seeker using <strong>IntelliResume AI</strong>
                    </div>
                </div>
            </div>
            
            <script>
                // Copy discount code to clipboard
                const discountCode = document.querySelector('.discount-code');
                if (discountCode) {{
                    discountCode.addEventListener('click', async () => {{
                        const code = discountCode.innerText;
                        await navigator.clipboard.writeText(code);
                        const original = discountCode.innerText;
                        discountCode.innerText = '✓ Copied!';
                        setTimeout(() => {{ discountCode.innerText = original; }}, 2000);
                    }});
                }}
            </script>
        </body>
        </html>
        """
        
        return html
    
    except Exception as e:
        return _render_error(f"Error loading share: {e}")


def _score_color(score: int) -> str:
    """Get color based on score"""
    if score >= 70:
        return "#00B050"  # Green
    elif score >= 50:
        return "#FFC000"  # Yellow
    else:
        return "#E7492E"  # Red


def _render_discount_section(discount_code: Optional[str], discount_percent: int, valid_until) -> str:
    """Render discount section if code exists"""
    if not discount_code:
        return ""
    
    valid_until_str = valid_until.strftime("%b %d") if valid_until else "24 hours"
    
    return f"""
    <div class="discount">
        🎉 <strong>Exclusive {discount_percent}% Off</strong> (Valid until {valid_until_str})
        <div class="discount-code" onclick="this.select()">{discount_code}</div>
        <p style="margin: 0; font-size: 12px; color: #666;">Click to copy • Use at checkout</p>
    </div>
    """


def _render_404() -> str:
    """Render 404 page"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Share Link Not Found</title>
        <meta property="og:title" content="Share Link Not Found">
    </head>
    <body style="background: #f5f5f5; padding: 40px; text-align: center; font-family: sans-serif;">
        <h1>Share Link Not Found</h1>
        <p>This share link has expired or doesn't exist.</p>
        <a href="https://intelliresume.ai">← Back to IntelliResume</a>
    </body>
    </html>
    """


def _render_error(message: str) -> str:
    """Render error page"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Error</title>
    </head>
    <body style="background: #f5f5f5; padding: 40px; text-align: center; font-family: sans-serif;">
        <h1>Error</h1>
        <p>{message}</p>
        <a href="https://intelliresume.ai">← Back to IntelliResume</a>
    </body>
    </html>
    """
