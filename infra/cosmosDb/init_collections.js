const { MongoClient } = require('mongodb');

// Connection string for your CosmosDB MongoDB API
const uri = "mongodb://mongo-sdt-uks-aid-dev1:PK8WirVV8QcSuchgUAy1HPMqo6bS3bTe8ae2JLooGDh4AfWFB9sTuhiYrKDjT7g9CsFkp2m2HABtACDbcGSvTA==@mongo-sdt-uks-aid-dev1.mongo.cosmos.azure.com:10255/?ssl=true&replicaSet=globaldb&retrywrites=false&maxIdleTimeMS=120000&appName=@mongo-sdt-uks-aid-dev1@";

// Create a new MongoClient
const client = new MongoClient(uri, { useNewUrlParser: true, useUnifiedTopology: true });

const collections = {
  schools: [
    { key: { _id: 1 } },
    { key: { is_deleted: 1 } },
    // Adding composite index on school_id and is_deleted for more efficient queries on deletion status
    { key: { _id: 1, is_deleted: 1 }, options: { unique: true } }
  ],
  teachers: [
    { key: { _id: 1 } },
    { key: { _id: 1, kinde_id: 1 }, options: { unique: true } },
    { key: { is_deleted: 1 } },
    { key: { kinde_id: 1, is_deleted: 1 } },
    { key: { school_id: 1, is_deleted: 1 } },
    // Adding composite index on school_id, kinde_id and is_deleted for better query performance
    { key: { school_id: 1, kinde_id: 1, is_deleted: 1 } }
  ],
  classgroups: [
    { key: { _id: 1 } },
    { key: { is_deleted: 1 } },
    { key: { teacher_id: 1, is_deleted: 1 } },
    { key: { student_ids: 1 } },
    // Composite index for teacher_id and is_deleted
    { key: { teacher_id: 1, is_deleted: 1 } }
  ],
  students: [
    { key: { _id: 1 } },
    { key: { is_deleted: 1 } },
    { key: { teacher_id: 1, is_deleted: 1 } },
    { key: { teacher_id: 1, _id: 1, is_deleted: 1 } },
    { key: { teacher_id: 1, external_student_id: 1 } },
    { key: { teacher_id: 1, year_group: 1, is_deleted: 1 } },
    // Composite index for teacher_id and year_group
    { key: { teacher_id: 1, year_group: 1, is_deleted: 1 } }
  ],
  assignments: [
    { key: { _id: 1 } },
    { key: { is_deleted: 1 } },
    { key: { class_group_id: 1, is_deleted: 1 } },
    // Adding composite index on class_group_id and is_deleted for better query performance
    { key: { class_group_id: 1, is_deleted: 1 } }
  ],
  documents: [
    { key: { _id: 1 } },
    { key: { is_deleted: 1 } },
    { key: { teacher_id: 1, is_deleted: 1 } },
    { key: { teacher_id: 1, _id: 1, is_deleted: 1 } },
    { key: { teacher_id: 1, student_id: 1, is_deleted: 1 } },
    { key: { teacher_id: 1, assignment_id: 1, is_deleted: 1 } },
    { key: { teacher_id: 1, status: 1, is_deleted: 1 } },
    { key: { teacher_id: 1, upload_timestamp: 1 } },
    { key: { batch_id: 1 } },
    { key: { batch_id: 1, status: 1 } },
    // Adding composite index on teacher_id, assignment_id and status for better query performance
    { key: { teacher_id: 1, assignment_id: 1, status: 1 } }
  ],
  results: [
    { key: { _id: 1 } },
    { key: { is_deleted: 1 } },
    { key: { document_id: 1, is_deleted: 1 } },
    { key: { teacher_id: 1, status: 1, score: 1, updated_at: 1 } },
    // Adding composite index on teacher_id, status and score for better query performance
    { key: { teacher_id: 1, status: 1, score: 1, updated_at: 1 } }
  ],
  batches: [
    { key: { _id: 1 } },
    // Adding composite index on status and created_at for better query performance
    { key: { status: 1, created_at: 1 } }
  ]
};

async function createCollectionsAndIndexes() {
  try {
    // Connect to MongoDB
    await client.connect();
    console.log("Connected to MongoDB");

    const db = client.db('aidetector_dev1'); // Use your database name

    for (const [collectionName, indexes] of Object.entries(collections)) {
      const coll = db.collection(collectionName);

      // Create collection if it doesn't exist (it is safe to check if collection exists before creation)
      const existingCollections = await db.listCollections().toArray();
      if (!existingCollections.some(c => c.name === collectionName)) {
        await db.createCollection(collectionName);
        console.log(`Created collection: ${collectionName}`);
      }

      // Get existing indexes for the collection
      const existingIndexes = await coll.indexes();

      for (const index of indexes) {
        const key = index.key;
        const options = index.options || {};

        // Check if the index already exists
        const indexExists = existingIndexes.some(i => JSON.stringify(i.key) === JSON.stringify(key));

        if (!indexExists) {
          try {
            await coll.createIndex(key, options);
            console.log(`✅ Created index on '${collectionName}': ${JSON.stringify(key)}`);
          } catch (e) {
            console.log(`❌ Failed to create index on '${collectionName}': ${JSON.stringify(key)}\n${e.message}`);
          }
        } else {
          console.log(`⚠️ Index already exists on '${collectionName}': ${JSON.stringify(key)}`);
        }
      }
    }

  } catch (err) {
    console.error("Error during collection and index creation:", err);
  } finally {
    // Close the connection when done
    await client.close();
  }
}

// Execute the function
createCollectionsAndIndexes().catch(console.error);
