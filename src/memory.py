from typing import Any, List, Dict
import os
import json # ADDED
import time
from typing import Any, List, Dict
import logging
# Conditional import for voyageai
try:
    import voyageai
except ImportError:
    voyageai = None
    logging.warning("voyageai package not found. Voyage AI embeddings will not be available.")

# Conditional import for chromadb
try:
    import chromadb
except ImportError:
    chromadb = None
    logging.warning("chromadb package not found. Vector memory will not be available.")

logger = logging.getLogger(__name__)


class Memory:
    def __init__(self):
        self.experiences = []
        self.goals: List[Dict[str, Any]] = [] # Change to list of dicts
        self.knowledge = {}
        self.messages = []

        self.voyage_ai_api_key = os.environ.get("VOYAGE_AI_API_KEY")
        self.enable_voyage_ai = os.environ.get("ENABLE_VOYAGE_AI", "no").lower() == "yes"
        self.voyageai_client = None
        self.voyage_embedding_model = "voyage-large-2" # Default embedding model

        if self.enable_voyage_ai and self.voyage_ai_api_key and voyageai:
            try:
                self.voyageai_client = voyageai.Client(api_key=self.voyage_ai_api_key)
                logger.info(f"Voyage AI client initialized with model: {self.voyage_embedding_model}")
            except Exception as e:
                logger.error(f"Failed to initialize Voyage AI client: {e}")
                self.voyageai_client = None
        elif self.enable_voyage_ai and not self.voyage_ai_api_key:
            logger.warning("ENABLE_VOYAGE_AI is 'yes' but VOYAGE_AI_API_KEY is not set. Voyage AI embeddings will not be available.")
        elif self.enable_voyage_ai and not voyageai:
            logger.warning("ENABLE_VOYAGE_AI is 'yes' but voyageai package is not installed. Voyage AI embeddings will not be available.")

        # Initialize ChromaDB for vector memory if Voyage AI is enabled and ChromaDB is available
        self.chroma_client = None
        self.chroma_collection = None
        if self.enable_voyage_ai and self.voyageai_client and chromadb:
            try:
                # Custom Embedding Function for ChromaDB using Voyage AI
                class VoyageAIEmbeddingFunction(chromadb.api.models.EmbeddingFunction):
                    def __init__(self, voyage_client, embedding_model):
                        self._voyage_client = voyage_client
                        self._embedding_model = embedding_model

                    def __call__(self, texts: chromadb.api.models.Collection.Documents) -> chromadb.api.models.Collection.Embeddings:
                        return self._voyage_client.embed(texts, model=self._embedding_model).embeddings

                self.chroma_client = chromadb.Client() # In-memory client
                self.chroma_collection = self.chroma_client.get_or_create_collection(
                    name="agent_memories",
                    embedding_function=VoyageAIEmbeddingFunction(self.voyageai_client, self.voyage_embedding_model)
                )
                logger.info("ChromaDB client and collection initialized for Voyage AI embeddings.")
            except Exception as e:
                logger.error(f"Failed to initialize ChromaDB for Voyage AI: {e}")
                self.chroma_client = None
                self.chroma_collection = None
        elif self.enable_voyage_ai and not chromadb:
            logger.warning("ENABLE_VOYAGE_AI is 'yes' but chromadb package is not installed. Vector memory will not be available.")

    def add_experience(self, experience: dict):
        """
        Adds an experience to the agent's memory.
        An experience typically includes task, plan, execution results, and reflection.
        If Voyage AI and ChromaDB are enabled, the experience is also stored in the vector database.
        """
        self.experiences.append(experience)

        if self.enable_voyage_ai and self.chroma_collection:
            try:
                # Convert experience dict to a string for embedding
                experience_str = json.dumps(experience, sort_keys=True, default=str)
                
                # Use a unique ID for each experience in ChromaDB
                experience_id = str(len(self.experiences) - 1) # Simple incremental ID

                self.chroma_collection.add(
                    documents=[experience_str],
                    metadatas=[{"timestamp": time.time(), "type": "experience"}],
                    ids=[experience_id]
                )
                logger.debug(f"Added experience to ChromaDB with ID: {experience_id}")
            except Exception as e:
                logger.error(f"Failed to add experience to ChromaDB: {e}")

    def get_all_experiences(self):
        """
        Retrieves all stored experiences.
        """
        return self.experiences

    def clear_memory(self):
        """
        Clears all stored experiences from memory.
        """
        self.experiences = []
        self.goals = [] # Clear goals too
        self.knowledge = {} # Clear knowledge too

    def add_goal(self, goal: str, priority: int = 5):
        """Adds a new goal to the agent's memory with a given priority (1=highest, 10=lowest)."""
        # Check if goal already exists to avoid duplicates based on description
        if not any(g['description'] == goal for g in self.goals):
            self.goals.append({"description": goal, "priority": priority, "timestamp": time.time()})
            # Sort goals by priority (ascending), then by timestamp (ascending) for stable order
            self.goals.sort(key=lambda x: (x['priority'], x['timestamp']))

    def get_goals(self) -> List[Dict[str, Any]]:
        """Retrieves all current goals, sorted by priority."""
        return self.goals

    def remove_goal(self, goal_description: str):
        """Removes a goal from the agent's memory by its description."""
        self.goals = [g for g in self.goals if g['description'] != goal_description]

    def add_knowledge(self, key: str, value: Any):
        """Adds or updates a piece of general knowledge."""
        self.knowledge[key] = value

    def get_knowledge(self, key: str, default: Any = None) -> Any:
        """Retrieves a piece of general knowledge by key."""
        return self.knowledge.get(key, default)

    def get_all_knowledge(self) -> dict:
        """Retrieves all stored general knowledge."""
        return self.knowledge

    def add_message(self, sender: str, message: str):
        """
        Adds an incoming message to the agent's memory.
        """
        self.messages.append({"sender": sender, "message": message, "timestamp": time.time()})

    def get_all_tips(self) -> list[str]:
        """Retrieves all distilled tips."""
        # In a real system, tips would be distilled from experiences.
        # For now, we'll return a placeholder or an empty list.
        return [] # Placeholder

    def retrieve_relevant_memories(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieves top N most relevant memories (experiences) from the vector database
        based on the query, using Voyage AI embeddings.
        """
        if not self.enable_voyage_ai or not self.chroma_collection:
            logger.warning("Voyage AI or ChromaDB not enabled/initialized. Cannot retrieve relevant memories.")
            return []
        
        try:
            # ChromaDB handles embedding the query using the collection's embedding function
            results = self.chroma_collection.query(
                query_texts=[query],
                n_results=n_results,
                include=['documents', 'distances', 'metadatas']
            )

            relevant_memories = []
            if results and results['documents']:
                for i in range(len(results['documents'][0])):
                    doc_str = results['documents'][0][i]
                    metadata = results['metadatas'][0][i]
                    distance = results['distances'][0][i]
                    
                    try:
                        # Convert the stored document string back to a dictionary
                        memory_dict = json.loads(doc_str)
                        memory_dict["_chroma_metadata"] = metadata
                        memory_dict["_chroma_distance"] = distance
                        relevant_memories.append(memory_dict)
                    except json.JSONDecodeError:
                        logger.error(f"Failed to decode stored memory JSON: {doc_str[:100]}...")
            return relevant_memories

        except Exception as e:
            logger.error(f"Error retrieving relevant memories from ChromaDB: {e}")
            return []

    def __len__(self):
        return len(self.experiences)

    def __str__(self):
        return f"Memory with {len(self.experiences)} experiences, {len(self.goals)} goals, and {len(self.knowledge)} knowledge items."

    def _get_embedding(self, text: str) -> List[float]:
        """
        Generates an embedding for the given text using Voyage AI.
        """
        if not self.enable_voyage_ai or not self.voyageai_client:
            logger.warning("Voyage AI is not enabled or client not initialized. Cannot generate embedding.")
            return []
        
        try:
            # Voyage AI client's embed method expects a list of texts
            response = self.voyageai_client.embed([text], model=self.voyage_embedding_model)
            if response.embeddings and len(response.embeddings) > 0:
                return response.embeddings[0]
            else:
                logger.error(f"Voyage AI returned no embeddings for text: {text[:50]}...")
                return []
        except Exception as e:
            logger.error(f"Error generating embedding with Voyage AI for text: {text[:50]}... Error: {e}")
            return []