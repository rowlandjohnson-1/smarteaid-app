from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import IndexModel, ASCENDING
from .database import get_database

async def init_db_indexes():
    """
    Initialize MongoDB indexes for collections.
    This should be called during application startup.
    """
    db = get_database()
    if not db:
        return False

    try:
        # Student Collection Indexes
        student_indexes = [
            # Index for internal ID (should be created automatically by MongoDB)
            IndexModel([("_id", ASCENDING)], name="internal_id_index"),
            
            # Sparse unique index for external_student_id
            # Only indexes documents where external_student_id exists
            IndexModel(
                [("external_student_id", ASCENDING)],
                name="external_student_id_unique",
                unique=True,
                sparse=True
            ),
            
            # Compound index for efficient filtering and sorting
            IndexModel(
                [
                    ("last_name", ASCENDING),
                    ("first_name", ASCENDING)
                ],
                name="name_lookup"
            )
        ]
        
        # Create indexes
        await db["students"].create_indexes(student_indexes)
        
        return True
    except Exception as e:
        print(f"Error creating indexes: {e}")
        return False 