from typing import List, Dict
import hashlib
import logging
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class DocumentProcessor:
    """Process documents with intelligent semantic chunking"""
    
    def __init__(self):
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            length_function=len,
            separators=[
                "\n\n\n",
                "\n\n",
                "\n",
                ". ",
                "! ",
                "? ",
                "; ",
                ", ",
                " ",
                ""
            ],
            keep_separator=True
        )
    
    def process(self, text: str, metadata: dict) -> List[Dict]:
        """Process document into semantic chunks"""
        
        # Clean text
        text = self._clean_text(text)
        
        # Split into chunks
        chunks_text = self.text_splitter.split_text(text)
        
        logger.info(f"Split document into {len(chunks_text)} chunks (avg {len(text)//len(chunks_text) if chunks_text else 0} chars/chunk)")
        
        # Generate document ID once
        doc_id = self._generate_doc_id(metadata['url'])
        
        # Create chunk objects
        chunks = []
        for i, chunk_text in enumerate(chunks_text):
            chunk_id = self._generate_chunk_id(metadata['url'], i)
            
            chunk = {
                'chunk_id': chunk_id,
                'document_id': doc_id,
                'text': chunk_text,
                'metadata': {
                    **metadata,
                    'document_id': doc_id,  # ADD THIS - include in metadata
                    'chunk_index': i,
                    'total_chunks': len(chunks_text),
                    'char_count': len(chunk_text),
                    'word_count': len(chunk_text.split())
                }
            }
            
            chunks.append(chunk)
        
        return chunks
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        import re
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        text = text.strip()
        return text
    
    def _generate_chunk_id(self, url: str, chunk_index: int) -> str:
        return hashlib.md5(f"{url}_{chunk_index}".encode()).hexdigest()
    
    def _generate_doc_id(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()