# app/api/v1/endpoints/dashboard.py

import logging
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, status, Depends
from datetime import datetime, timezone
from pydantic import BaseModel

# Import authentication dependency
from app.core.security import get_current_user_payload

# Import CRUD functions
from app.db import crud

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
    summary="Get dashboard statistics",
    description="Retrieves various statistics for the dashboard including total assessed documents, average score, and more."
)
async def get_dashboard_stats(
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """Protected endpoint to get dashboard statistics."""
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} requesting dashboard statistics")
    
    try:
        stats = await crud.get_dashboard_stats()
        return stats
    except Exception as e:
        logger.error(f"Error fetching dashboard stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch dashboard statistics"
        )

@router.get(
    "/score-distribution",
    response_model=ScoreDistributionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get score distribution",
    description="Retrieves the distribution of AI scores across different ranges (0-20, 21-40, 41-60, 61-80, 81-100)."
)
async def get_score_distribution(
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """Protected endpoint to get score distribution data."""
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} requesting score distribution")
    
    try:
        result = await crud.get_score_distribution()
        
        return ScoreDistributionResponse(
            distribution=[ScoreDistributionItem(**item) for item in result["distribution"]],
            total_documents=result["total_documents"]
        )
    except Exception as e:
        logger.error(f"Error fetching score distribution: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch score distribution"
        )