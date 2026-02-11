import asyncio
from playwright.async_api import async_playwright
import fitz
import aiohttp
from bs4 import BeautifulSoup
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)

class DocumentScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    async def scrape(self, url: str) -> Tuple[str, dict]:
        """Scrape document and return (text, metadata)"""
        doc_type = self._detect_type(url)
        
        if doc_type == "pdf":
            return await self._scrape_pdf(url)
        else:
            return await self._scrape_webpage(url)
    
    def _detect_type(self, url: str) -> str:
        return "pdf" if url.lower().endswith('.pdf') else "webpage"
    
    async def _scrape_webpage(self, url: str) -> Tuple[str, dict]:
        """Scrape webpage using Playwright"""
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, wait_until='networkidle', timeout=30000)
                
                title = await page.title()
                content = await page.content()
                await browser.close()
                
                soup = BeautifulSoup(content, 'lxml')
                
                for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                    tag.decompose()
                
                text_parts = []
                for heading in soup.find_all(['h1', 'h2', 'h3', 'h4']):
                    text_parts.append(f"\n{heading.get_text().strip()}\n")
                
                for elem in soup.find_all(['p', 'li', 'article', 'section']):
                    text = elem.get_text().strip()
                    if text and len(text) > 20:
                        text_parts.append(text)
                
                full_text = '\n\n'.join(text_parts)
                
                metadata = {
                    'url': url,
                    'title': title,
                    'type': 'webpage',
                    'length': len(full_text)
                }
                
                return full_text, metadata
                
        except Exception as e:
            logger.error(f"Error scraping webpage {url}: {e}")
            raise
    
    async def _scrape_pdf(self, url: str) -> Tuple[str, dict]:
        """Download and extract text from PDF"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as response:
                    pdf_bytes = await response.read()
            
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            
            text_parts = []
            for page_num in range(len(doc)):
                page = doc[page_num]
                blocks = page.get_text("blocks")
                
                for block in blocks:
                    text = block[4].strip()
                    if text and len(text) > 10:
                        text_parts.append(text)
            
            full_text = '\n\n'.join(text_parts)
            
            metadata = {
                'url': url,
                'title': doc.metadata.get('title', 'Untitled PDF'),
                'type': 'pdf',
                'pages': len(doc),
                'length': len(full_text)
            }
            
            doc.close()
            return full_text, metadata
            
        except Exception as e:
            logger.error(f"Error scraping PDF {url}: {e}")
            raise