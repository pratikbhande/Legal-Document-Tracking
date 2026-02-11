from openai import OpenAI
import json
import logging
from typing import Dict, List, Optional
from app.config import get_settings
from app.prompts import ARTICLE_ANALYSIS_PROMPT, LAW_REFERENCE_VALIDATION_PROMPT

logger = logging.getLogger(__name__)
settings = get_settings()

class DocumentAnalyzer:
    def __init__(self):
        self.client = OpenAI(api_key=settings.openai_api_key)
    
    async def validate_law_reference(self, document_text: str, law_name: str) -> bool:
        """
        Quick validation: Does this document actually reference the law?
        Returns True if document references the law, False otherwise
        """
        try:
            # Truncate document for quick check (first 3000 chars usually enough)
            sample_text = document_text[:3000]
            
            prompt = LAW_REFERENCE_VALIDATION_PROMPT.format(
                law_name=law_name,
                document_text=sample_text
            )
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",  # Cheap and fast
                messages=[
                    {"role": "system", "content": "You are a legal document analyzer. Respond concisely."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=50
            )
            
            result = response.choices[0].message.content.strip()
            
            # Parse YES/NO
            is_valid = result.upper().startswith('YES')
            
            logger.info(f"Validation for '{law_name}': {result[:100]}")
            
            return is_valid
        
        except Exception as e:
            logger.error(f"Error in validation: {e}")
            # On error, be conservative and include the document
            return True
    
    async def analyze_document(
        self,
        document_text: str,
        law_name: str,
        what_changed: str
    ) -> Dict:
        """Detailed analysis with change suggestions"""
        
        try:
            prompt = ARTICLE_ANALYSIS_PROMPT.format(
                law_name=law_name,
                what_changed=what_changed,
                document_text=document_text[:15000]
            )
            
            response = self.client.chat.completions.create(
                model=settings.analysis_model,
                messages=[
                    {"role": "system", "content": "You are a legal compliance expert. Respond only with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            return result.get('analysis', {})
        
        except Exception as e:
            logger.error(f"Error analyzing document: {e}")
            return {
                "document_mentions_law": False,
                "overall_impact": f"Error during analysis: {str(e)}",
                "sections_needing_update": []
            }
    
    def combine_chunks_for_analysis(self, chunks: List[Dict]) -> str:
        """Combine chunks into full document text"""
        sorted_chunks = sorted(
            chunks,
            key=lambda x: (
                x.get('metadata', {}).get('section_index', 0) if isinstance(x.get('metadata'), dict) else 0,
                x.get('metadata', {}).get('chunk_index', 0) if isinstance(x.get('metadata'), dict) else 0
            )
        )
        
        texts = [chunk.get('text', '') for chunk in sorted_chunks]
        return '\n\n'.join(texts)