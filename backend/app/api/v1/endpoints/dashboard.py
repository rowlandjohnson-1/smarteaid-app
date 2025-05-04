# app/api/v1/endpoints/dashboard.py

import logging
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, status, Depends, Query
from datetime import datetime, timezone
from pydantic import BaseModel
import uuid # Added for potential future use

# Import authentication dependency
from app.core.security import get_current_user_payload

# Import CRUD functions
from app.db import crud
# Import Document model for response type
from app.models.document import Document
from app.models.teacher import Teacher  # Import Teacher model

# Setup logger
logger = logging.getLogger(__name__)

# Create router instance
router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)

# Define response models
class ScoreDistributionItem(BaseModel):
    range: str
    count: int

class ScoreDistributionResponse(BaseModel):
    distribution: List[ScoreDistributionItem]
    total_documents: int

@router.get(
    "/stats",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Get dashboard statistics (User specific)",
    description="Retrieves various statistics for the current authenticated teacher's dashboard."
)
async def get_dashboard_stats_endpoint(
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """Protected endpoint to get dashboard statistics for the current user."""
    logger.info(f"Endpoint /dashboard/stats called. Payload sub: {current_user_payload.get('sub')}")
    try:
        stats = await crud.get_dashboard_stats(current_user_payload)
        logger.info(f"Endpoint /dashboard/stats returning stats.")
        return stats
    except Exception as e:
        logger.error(f"!!! EXCEPTION IN /dashboard/stats ENDPOINT: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error fetching dashboard stats.")

@router.get(
    "/score-distribution",
    response_model=ScoreDistributionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get score distribution (User specific)",
    description="Retrieves the distribution of AI scores across different ranges for the current authenticated teacher."
)
async def get_score_distribution_endpoint(
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """Protected endpoint to get score distribution data for the current user."""
    logger.info(f"Endpoint /dashboard/score-distribution called. Payload sub: {current_user_payload.get('sub')}")
    try:
        result = await crud.get_score_distribution(current_user_payload)
        if result is None or not result.get("distribution"):
            logger.warning(f"Score distribution data not found or empty for user {current_user_payload.get('sub')}. Returning empty.")
            return ScoreDistributionResponse(distribution=[], total_documents=0)

        logger.info(f"Endpoint /dashboard/score-distribution returning distribution.")
        return ScoreDistributionResponse(
            distribution=[ScoreDistributionItem(**item) for item in result["distribution"]],
            total_documents=result.get("total_documents", 0)
        )
    except Exception as e:
        logger.error(f"!!! EXCEPTION IN /dashboard/score-distribution ENDPOINT: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error fetching score distribution.")

@router.get("/recent", response_model=List[Document])
async def get_recent_documents(
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Get the most recent documents for the current user.
    """
    logger.info(f"Endpoint /dashboard/recent called. Payload sub: {current_user_payload.get('sub')}")
    try:
        # Get the teacher's Kinde ID from the payload
        teacher_id = current_user_payload.get("sub")
        if not teacher_id:
            logger.error("User ID (sub) not found in token payload for /dashboard/recent")
            raise HTTPException(status_code=400, detail="User ID not found in token")
            
        # Get recent documents
        documents = await crud.get_recent_documents(teacher_id=teacher_id)
        logger.info(f"Endpoint /dashboard/recent returning {len(documents)} documents.")
        return documents
        
    except Exception as e:
        logger.error(f"Error in /dashboard/recent: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))