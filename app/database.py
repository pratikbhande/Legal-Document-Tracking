from motor.motor_asyncio import AsyncIOMotorClient
from typing import List, Dict, Optional, Any
import logging
from datetime import datetime
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class MongoDB:
    def __init__(self):
        self.client = None
        self.db = None
    
    async def connect(self):
        """Connect to MongoDB"""
        self.client = AsyncIOMotorClient(settings.mongodb_url)
        self.db = self.client[settings.database_name]
        logger.info("Connected to MongoDB")
    
    async def close(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            logger.info("Closed MongoDB connection")
    
    # Documents collection
    async def insert_document(self, doc: Dict):
        """Insert indexed document metadata"""
        await self.db.documents.insert_one(doc)
    
    async def get_document(self, document_id: str) -> Optional[Dict]:
        """Get document by ID"""
        doc = await self.db.documents.find_one(
            {"document_id": document_id},
            {"_id": 0}
        )
        return doc
    
    # Flags collection
    async def create_flag(self, flag: Dict):
        """Create a flag for a document"""
        flag["created_at"] = datetime.utcnow()
        await self.db.flags.update_one(
            {"document_id": flag["document_id"]},
            {"$set": flag},
            upsert=True
        )
    
    async def get_all_flags(self) -> List[Dict]:
        """Get all flagged documents"""
        cursor = self.db.flags.find({}, {"_id": 0})
        return await cursor.to_list(length=None)
    
    async def get_flag(self, document_id: str) -> Optional[Dict]:
        """Get flag for specific document"""
        flag = await self.db.flags.find_one(
            {"document_id": document_id},
            {"_id": 0}
        )
        return flag
    
    async def update_flag_status(self, document_id: str, status: str):
        """Update flag status"""
        await self.db.flags.update_one(
            {"document_id": document_id},
            {"$set": {"status": status, "reviewed_at": datetime.utcnow()}}
        )
    
    async def delete_flags(self, document_ids: List[str]):
        """Delete flags for documents"""
        await self.db.flags.delete_many({"document_id": {"$in": document_ids}})
    
    # Jobs collection
    async def create_job(self, job_id: str, job_type: str, params: Dict) -> Dict:
        """Create a background job"""
        job = {
            "job_id": job_id,
            "type": job_type,
            "status": "pending",
            "params": params,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "result": None,
            "error": None
        }
        await self.db.jobs.insert_one(job)
        return job
    
    async def update_job(self, job_id: str, status: str, result: Any = None, error: str = None):
        """Update job status"""
        update = {
            "status": status,
            "updated_at": datetime.utcnow()
        }
        if result is not None:
            update["result"] = result
        if error is not None:
            update["error"] = error
        
        await self.db.jobs.update_one(
            {"job_id": job_id},
            {"$set": update}
        )
    
    async def get_job(self, job_id: str) -> Optional[Dict]:
        """Get job by ID"""
        job = await self.db.jobs.find_one(
            {"job_id": job_id},
            {"_id": 0}
        )
        return job
    
    # DELETE ALL DATA
    async def delete_all_data(self) -> Dict:
        """Delete all data from MongoDB"""
        try:
            # Delete all documents
            doc_result = await self.db.documents.delete_many({})
            
            # Delete all flags
            flag_result = await self.db.flags.delete_many({})
            
            # Delete all jobs
            job_result = await self.db.jobs.delete_many({})
            
            logger.info(
                f"Deleted all MongoDB data: "
                f"{doc_result.deleted_count} docs, "
                f"{flag_result.deleted_count} flags, "
                f"{job_result.deleted_count} jobs"
            )
            
            return {
                "status": "success",
                "deleted": {
                    "documents": doc_result.deleted_count,
                    "flags": flag_result.deleted_count,
                    "jobs": job_result.deleted_count
                }
            }
        
        except Exception as e:
            logger.error(f"Error deleting MongoDB data: {e}")
            return {"status": "error", "message": str(e)}

# Global instance
mongodb = MongoDB()