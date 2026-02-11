import chromadb
from chromadb.config import Settings as ChromaSettings
from openai import OpenAI
from typing import List, Dict
import logging
import re
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class VectorDB:
    """ChromaDB with OpenAI embeddings + simple proximity keyword search"""
    
    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False)
        )
        self.openai_client = OpenAI(api_key=settings.openai_api_key)
        self.collection = self._get_or_create_collection()
    
    def _get_or_create_collection(self):
        """Create collection for OpenAI embeddings (1536 dimensions)"""
        collection_name = "legal_documents"
        
        try:
            collection = self.client.get_collection(collection_name)
            logger.info(f"Using existing collection: {collection_name}")
            return collection
        except:
            logger.info(f"Creating new collection: {collection_name}")
            return self.client.create_collection(
                name=collection_name,
                metadata={
                    "hnsw:space": "cosine",
                    "dimension": 1536
                }
            )
    
    def _get_embedding(self, text: str) -> List[float]:
        """Get OpenAI embedding"""
        response = self.openai_client.embeddings.create(
            model=settings.embedding_model,
            input=text[:8000]
        )
        return response.data[0].embedding
    
    def _batch_embeddings(self, texts: List[str], batch_size: int = 100) -> List[List[float]]:
        """Get embeddings in batches for efficiency"""
        embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch = [text[:8000] for text in batch]
            
            response = self.openai_client.embeddings.create(
                model=settings.embedding_model,
                input=batch
            )
            
            batch_embeddings = [item.embedding for item in response.data]
            embeddings.extend(batch_embeddings)
            
            logger.info(f"Generated embeddings for batch {i//batch_size + 1} ({len(batch)} texts)")
        
        return embeddings
    
    async def index_chunks(self, chunks: List[Dict]) -> int:
        """Index document chunks with batched embeddings"""
        if not chunks:
            return 0
        
        ids = [c['chunk_id'] for c in chunks]
        texts = [c['text'] for c in chunks]
        metadatas = [c['metadata'] for c in chunks]
        
        logger.info(f"Generating embeddings for {len(texts)} chunks...")
        
        embeddings = self._batch_embeddings(texts)
        
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas
        )
        
        logger.info(f"✅ Indexed {len(chunks)} chunks successfully")
        return len(chunks)
    
    async def find_all_matching_documents(self, law_name: str, threshold: float = 0.3) -> List[Dict]:
        """
        Hybrid search: Semantic (embeddings) + Keyword (proximity)
        """
        
        logger.info(f"🔍 Hybrid search for: '{law_name}'")
        
        # 1. Semantic search using OpenAI embeddings
        semantic_results = await self._semantic_search(law_name, threshold)
        logger.info(f"   Semantic search found: {len(semantic_results)} documents")
        
        # 2. Keyword search (simple proximity)
        keyword_results = await self._keyword_search(law_name)
        logger.info(f"   Keyword search found: {len(keyword_results)} documents")
        
        # 3. Merge results
        merged = self._merge_results(semantic_results, keyword_results)
        
        logger.info(f"✅ Total unique documents: {len(merged)}")
        
        return merged
    
    async def _semantic_search(self, query: str, threshold: float) -> Dict[str, Dict]:
        """Semantic similarity search using OpenAI embeddings"""
        query_embedding = self._get_embedding(query)
        
        total_chunks = self.collection.count()
        search_limit = min(1000, total_chunks)
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=search_limit,
            include=['documents', 'metadatas', 'distances']
        )
        
        doc_matches = {}
        
        for chunk_id, doc, metadata, distance in zip(
            results['ids'][0],
            results['documents'][0],
            results['metadatas'][0],
            results['distances'][0]
        ):
            similarity = 1 - distance
            
            if similarity >= threshold:
                doc_id = metadata.get('document_id')
                if not doc_id:
                    logger.warning(f"Missing document_id in metadata for chunk {chunk_id}")
                    continue
                
                if doc_id not in doc_matches:
                    doc_matches[doc_id] = {
                        'document_id': doc_id,
                        'url': metadata.get('url'),
                        'title': metadata.get('title'),
                        'type': metadata.get('type'),
                        'chunks': [],
                        'semantic_score': similarity,
                        'keyword_score': 0.0
                    }
                else:
                    doc_matches[doc_id]['semantic_score'] = max(
                        doc_matches[doc_id]['semantic_score'],
                        similarity
                    )
                
                doc_matches[doc_id]['chunks'].append({
                    'chunk_id': chunk_id,
                    'text': doc
                })
        
        return doc_matches
    
    async def _keyword_search(self, query: str) -> Dict[str, Dict]:
        """
        Simple proximity-based keyword search
        Finds documents where query words appear close together (within ~15 words)
        """
        all_results = self.collection.get(
            include=['documents', 'metadatas']
        )
        
        if not all_results['ids']:
            return {}
        
        # Extract important words from query (ignore common words)
        stop_words = {'the', 'a', 'an', 'and', 'or', 'of', 'in', 'on', 'at', 'to', 'for', 'with', 'by'}
        query_words = [w.lower() for w in query.split() if w.lower() not in stop_words and len(w) > 2]
        
        if len(query_words) < 2:
            logger.info(f"Query too short for keyword search: {query_words}")
            return {}
        
        logger.info(f"Keyword search for words: {query_words}")
        
        doc_matches = {}
        max_distance = 15  # Words must be within 15 words of each other
        
        for chunk_id, doc_text, metadata in zip(
            all_results['ids'],
            all_results['documents'],
            all_results['metadatas']
        ):
            doc_lower = doc_text.lower()
            words = doc_lower.split()
            
            # Find positions of each query word
            word_positions = {}
            for query_word in query_words:
                positions = [i for i, w in enumerate(words) if query_word in w]
                if positions:
                    word_positions[query_word] = positions
            
            # Need at least 70% of query words present
            found_count = len(word_positions)
            required_count = max(2, int(len(query_words) * 0.7))
            
            if found_count < required_count:
                continue
            
            # Check if words appear close together
            min_span = float('inf')
            
            # Try to find the tightest window containing all found words
            from itertools import product
            try:
                for positions in product(*word_positions.values()):
                    span = max(positions) - min(positions)
                    min_span = min(min_span, span)
                    
                    # Early exit if we found perfect proximity
                    if min_span <= max_distance:
                        break
            except:
                continue
            
            # Score based on proximity
            if min_span <= max_distance:
                score = 1.0  # Perfect - all words within 15 words
            elif min_span <= max_distance * 2:
                score = 0.7  # Good - within 30 words
            elif min_span <= max_distance * 3:
                score = 0.4  # Acceptable - within 45 words
            else:
                continue  # Too scattered, skip
            
            # Boost score if all query words are present
            if found_count == len(query_words):
                score = min(1.0, score * 1.2)
            
            doc_id = metadata.get('document_id')
            if not doc_id:
                logger.warning(f"Missing document_id in metadata for chunk {chunk_id}")
                continue
            
            if doc_id not in doc_matches:
                doc_matches[doc_id] = {
                    'document_id': doc_id,
                    'url': metadata.get('url'),
                    'title': metadata.get('title'),
                    'type': metadata.get('type'),
                    'chunks': [],
                    'semantic_score': 0.0,
                    'keyword_score': score
                }
            else:
                doc_matches[doc_id]['keyword_score'] = max(
                    doc_matches[doc_id]['keyword_score'],
                    score
                )
            
            doc_matches[doc_id]['chunks'].append({
                'chunk_id': chunk_id,
                'text': doc_text
            })
        
        logger.info(f"Keyword search found {len(doc_matches)} documents")
        return doc_matches
    
    def _merge_results(self, semantic: Dict[str, Dict], keyword: Dict[str, Dict]) -> List[Dict]:
        """Merge semantic and keyword search results"""
        all_doc_ids = set(semantic.keys()) | set(keyword.keys())
        
        merged = []
        
        for doc_id in all_doc_ids:
            sem_data = semantic.get(doc_id, {})
            kw_data = keyword.get(doc_id, {})
            
            sem_score = sem_data.get('semantic_score', 0.0)
            kw_score = kw_data.get('keyword_score', 0.0)
            
            base_data = sem_data if sem_data else kw_data
            
            # Combine chunks (deduplicate by chunk_id)
            all_chunks = {}
            for chunk in sem_data.get('chunks', []):
                all_chunks[chunk['chunk_id']] = chunk
            for chunk in kw_data.get('chunks', []):
                all_chunks[chunk['chunk_id']] = chunk
            
            # Calculate combined confidence
            if sem_score > 0 and kw_score > 0:
                confidence = max(sem_score, kw_score)
                match_type = 'semantic+keyword'
            elif sem_score > 0:
                confidence = sem_score
                match_type = 'semantic'
            else:
                confidence = kw_score
                match_type = 'keyword'
            
            merged.append({
                'document_id': doc_id,
                'url': base_data.get('url'),
                'title': base_data.get('title'),
                'type': base_data.get('type'),
                'chunks': list(all_chunks.values()),
                'confidence': confidence,
                'match_type': match_type,
                'semantic_score': sem_score,
                'keyword_score': kw_score
            })
        
        # Sort by confidence
        merged.sort(key=lambda x: x['confidence'], reverse=True)
        
        return merged
    
    async def delete_all(self) -> Dict:
        """Delete entire collection and recreate"""
        try:
            self.client.delete_collection("legal_documents")
            logger.info("Deleted ChromaDB collection")
            
            self.collection = self._get_or_create_collection()
            logger.info("Recreated ChromaDB collection")
            
            return {"status": "success", "message": "Vector database cleared"}
        
        except Exception as e:
            logger.error(f"Error deleting ChromaDB: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_stats(self) -> Dict:
        return {
            'total_chunks': self.collection.count(),
            'collection_name': self.collection.name
        }