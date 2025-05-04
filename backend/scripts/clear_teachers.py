#!/usr/bin/env python3
"""
Script to clear all teachers from the database.
This is a destructive operation and should be used with caution.
"""

import asyncio
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.db.crud import clear_all_teachers

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    """Main function to clear all teachers."""
    # Connect to MongoDB
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB]
    
    try:
        # Confirm with user
        print("\nWARNING: This will delete ALL teachers from the database!")
        print("This operation cannot be undone.")
        confirmation = input("\nType 'DELETE' to confirm: ")
        
        if confirmation != "DELETE":
            print("Operation cancelled.")
            return
        
        # Clear all teachers
        success = await clear_all_teachers()
        
        if success:
            print("\nSuccessfully cleared all teachers from the database.")
        else:
            print("\nFailed to clear teachers from the database.")
            
    except Exception as e:
        logger.error(f"Error during script execution: {e}", exc_info=True)
        print(f"\nAn error occurred: {e}")
    finally:
        # Close the MongoDB connection
        client.close()

if __name__ == "__main__":
    asyncio.run(main()) 