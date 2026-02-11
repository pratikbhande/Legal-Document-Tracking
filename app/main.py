from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
import logging
from contextlib import asynccontextmanager
from datetime import datetime
import uuid

from app.models import *
from app.database import mongodb
from app.scraper import DocumentScraper
from app.processor import DocumentProcessor
from app.vectordb import VectorDB
from app.analyzer import DocumentAnalyzer
from app.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

settings = get_settings()

scraper = DocumentScraper()
processor = DocumentProcessor()
vector_db = VectorDB()
analyzer = DocumentAnalyzer()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown"""
    logger.info("Starting Legal Document Indexer API")
    
    # Connect to MongoDB
    await mongodb.connect()
    
    # Install playwright
    try:
        import subprocess
        subprocess.run(["playwright", "install", "chromium"], check=True, capture_output=True)
    except Exception as e:
        logger.warning(f"Playwright install: {e}")
    
    yield
    
    await mongodb.close()
    logger.info("Shutdown complete")

app = FastAPI(
    title="Legal Document Indexer",
    description="Index legal documents and flag when laws change",
    version="2.0.0",
    lifespan=lifespan
)

# ==================== INDEXING ====================

@app.post("/index/bulk", response_model=JobResponse)
async def bulk_index(request: BulkIndexRequest, background_tasks: BackgroundTasks):
    """Index multiple URLs in background"""
    job_id = str(uuid.uuid4())
    
    await mongodb.create_job(
        job_id=job_id,
        job_type="bulk_index",
        params={"urls": [str(url) for url in request.urls]}
    )
    
    background_tasks.add_task(_bulk_index_task, job_id, [str(url) for url in request.urls])
    
    return JobResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        message=f"Indexing {len(request.urls)} documents"
    )

async def _bulk_index_task(job_id: str, urls: List[str]):
    """Background task to index multiple documents"""
    try:
        await mongodb.update_job(job_id, "processing")
        
        indexed_count = 0
        failed_urls = []
        
        for url in urls:
            try:
                logger.info(f"Indexing: {url}")
                
                # Scrape
                text, metadata = await scraper.scrape(url)
                
                # Process
                chunks = processor.process(text, metadata)
                
                # Index
                await vector_db.index_chunks(chunks)
                
                # Save to MongoDB
                await mongodb.insert_document({
                    "document_id": chunks[0]['document_id'],
                    "url": url,
                    "title": metadata.get('title'),
                    "type": metadata.get('type'),
                    "indexed_at": datetime.utcnow(),
                    "chunk_count": len(chunks)
                })
                
                indexed_count += 1
                
            except Exception as e:
                logger.error(f"Failed to index {url}: {e}")
                failed_urls.append({"url": url, "error": str(e)})
        
        result = {
            "indexed": indexed_count,
            "failed": len(failed_urls),
            "failed_urls": failed_urls
        }
        
        await mongodb.update_job(job_id, "completed", result=result)
        logger.info(f"Bulk indexing complete: {indexed_count} indexed, {len(failed_urls)} failed")
        
    except Exception as e:
        logger.error(f"Bulk indexing job failed: {e}")
        await mongodb.update_job(job_id, "failed", error=str(e))

# ==================== FLAGGING ====================

@app.post("/flag", response_model=FlagResponse)
async def flag_documents(request: FlagRequest, background_tasks: BackgroundTasks):
    """Flag documents referencing a changed law"""
    job_id = str(uuid.uuid4())
    
    await mongodb.create_job(
        job_id=job_id,
        job_type="flag_documents",
        params={
            "law": request.changed_law,
            "what_changed": request.what_changed,
            "threshold": request.similarity_threshold
        }
    )
    
    background_tasks.add_task(
        _flag_documents_task,
        job_id,
        request.changed_law,
        request.what_changed,
        request.similarity_threshold
    )
    
    return FlagResponse(
        job_id=job_id,
        status="processing",
        total_documents_found=0,
        message="Searching and flagging documents..."
    )

async def _flag_documents_task(
    job_id: str,
    law_name: str,
    what_changed: Optional[str],
    threshold: float
):
    """Background task to flag documents with validation"""
    try:
        await mongodb.update_job(job_id, "processing")
        
        # STEP 1: Find ALL matching documents via hybrid search
        logger.info(f"Finding documents mentioning: {law_name}")
        matching_docs = await vector_db.find_all_matching_documents(law_name, threshold)
        
        logger.info(f"Hybrid search found {len(matching_docs)} candidate documents")
        
        # STEP 2: Validate each candidate with LLM
        logger.info(f"Validating candidates with LLM...")
        validated_docs = []
        
        for doc in matching_docs:
            # Combine chunks for validation
            full_text = analyzer.combine_chunks_for_analysis(doc['chunks'])
            
            # Quick LLM check: Does this document actually reference the law?
            is_valid = await analyzer.validate_law_reference(full_text, law_name)
            
            if is_valid:
                validated_docs.append(doc)
                logger.info(f"✅ Validated: {doc['title']}")
            else:
                logger.info(f"❌ Filtered out: {doc['title']}")
        
        logger.info(f"After validation: {len(validated_docs)} documents actually reference '{law_name}'")
        
        # STEP 3: Flag validated documents
        flagged_count = 0
        flagged_docs_summary = []
        
        for doc in validated_docs:
            try:
                full_text = analyzer.combine_chunks_for_analysis(doc['chunks'])
                
                flag_data = {
                    "document_id": doc['document_id'],
                    "url": doc['url'],
                    "title": doc['title'],
                    "flagged_for_law": law_name,
                    "what_changed": what_changed,
                    "confidence": doc['confidence'],
                    "status": "flagged",
                    "flagged_at": datetime.utcnow(),
                    "change_suggestions": []
                }
                
                # STEP 4: If what_changed provided, do detailed analysis
                if what_changed:
                    logger.info(f"Analyzing document: {doc['title']}")
                    
                    analysis = await analyzer.analyze_document(
                        full_text,
                        law_name,
                        what_changed
                    )
                    
                    flag_data["analysis"] = analysis
                    flag_data["change_suggestions"] = analysis.get("sections_needing_update", [])
                    
                    logger.info(f"Found {len(flag_data['change_suggestions'])} suggestions for {doc['title']}")
                
                await mongodb.create_flag(flag_data)
                flagged_count += 1
                
                # Add to summary
                flagged_docs_summary.append({
                    'document_id': doc['document_id'],
                    'title': doc['title'],
                    'url': doc['url'],
                    'suggestions_count': len(flag_data['change_suggestions'])
                })
                
            except Exception as e:
                logger.error(f"Error flagging document {doc['document_id']}: {e}")
        
        result = {
            "total_found": len(matching_docs),
            "validated": len(validated_docs),
            "flagged": flagged_count,
            "analyzed": flagged_count if what_changed else 0,
            "flagged_documents": flagged_docs_summary,
            "message": f"Successfully flagged {flagged_count} documents. Use GET /flagged to see detailed suggestions."
        }
        
        await mongodb.update_job(job_id, "completed", result=result)
        logger.info(f"Flagging complete: {flagged_count} documents flagged (filtered {len(matching_docs) - len(validated_docs)} false positives)")
        
    except Exception as e:
        logger.error(f"Flagging job failed: {e}")
        await mongodb.update_job(job_id, "failed", error=str(e))


# ==================== QUERY FLAGGED ====================

@app.get("/flagged", response_model=FlaggedListResponse)
async def get_flagged_documents(status: Optional[FlagStatus] = None):
    """Get all flagged documents"""
    try:
        flags = await mongodb.get_all_flags()
        
        # Filter by status if provided
        if status:
            flags = [f for f in flags if f.get('status') == status]
        
        # Format response
        flagged_docs = []
        for flag in flags:
            flagged_docs.append(FlaggedDocument(
                document_id=flag['document_id'],
                url=flag['url'],
                title=flag['title'],
                flagged_for_law=flag['flagged_for_law'],
                what_changed=flag.get('what_changed'),
                change_suggestions=[
                    ChangeSuggestion(**s) for s in flag.get('change_suggestions', [])
                ],
                status=flag.get('status', 'flagged'),
                confidence=flag['confidence'],
                flagged_at=flag['flagged_at'],
                reviewed_at=flag.get('reviewed_at')
            ))
        
        return FlaggedListResponse(
            flagged_documents=flagged_docs,
            total=len(flagged_docs)
        )
    
    except Exception as e:
        logger.error(f"Error getting flagged documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/flagged/{document_id}")
async def get_flagged_document(document_id: str):
    """Get specific flagged document details"""
    flag = await mongodb.get_flag(document_id)
    
    if not flag:
        raise HTTPException(status_code=404, detail="Flagged document not found")
    
    return flag

# ==================== UPDATE FLAGS ====================

@app.post("/flag/status")
async def update_flag_status(request: UpdateFlagStatusRequest):
    """Update flag status (flagged → reviewed → updated)"""
    try:
        await mongodb.update_flag_status(request.document_id, request.status)
        
        return {
            "status": "success",
            "document_id": request.document_id,
            "new_status": request.status
        }
    except Exception as e:
        logger.error(f"Error updating flag status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/unflag")
async def unflag_documents(request: UnflagRequest):
    """Remove flags from documents"""
    try:
        await mongodb.delete_flags(request.document_ids)
        
        return {
            "status": "success",
            "unflagged_count": len(request.document_ids)
        }
    except Exception as e:
        logger.error(f"Error unflagging: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== RESET/DELETE ====================

@app.delete("/reset", status_code=200)
async def reset_system():
    """
    ⚠️ DANGER: Delete ALL data from system
    Clears:
    - All ChromaDB vectors
    - All MongoDB documents
    - All flags
    - All jobs
    """
    try:
        logger.warning("🔥 RESET SYSTEM - Deleting all data")
        
        # Delete from Vector DB
        vector_result = await vector_db.delete_all()
        
        # Delete from MongoDB
        mongo_result = await mongodb.delete_all_data()
        
        result = {
            "status": "success",
            "message": "All data deleted successfully",
            "vector_db": vector_result,
            "mongodb": mongo_result
        }
        
        logger.warning("✅ System reset complete")
        return result
    
    except Exception as e:
        logger.error(f"Error resetting system: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== JOBS ====================

@app.get("/job/{job_id}")
async def get_job_status(job_id: str):
    """Get job status"""
    job = await mongodb.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return job

# ==================== HEALTH ====================

@app.get("/health")
async def health_check():
    """Health check"""
    try:
        stats = vector_db.get_stats()
        doc_count = await mongodb.db.documents.count_documents({})
        flag_count = await mongodb.db.flags.count_documents({})
        
        return {
            "status": "healthy",
            "stats": {
                **stats,
                "total_documents": doc_count,
                "total_flagged": flag_count
            }
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )

@app.get("/")
async def root():
    return {
        "service": "Legal Document Indexer",
        "version": "2.0.0",
        "endpoints": {
            "index": "POST /index/bulk",
            "flag": "POST /flag",
            "flagged": "GET /flagged",
            "unflag": "POST /unflag",
            "reset": "DELETE /reset",
            "job": "GET /job/{job_id}",
            "health": "GET /health"
        }
    }