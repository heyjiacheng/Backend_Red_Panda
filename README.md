# Backend_Red_Panda

## Environment Setup

Install Ollama from the [official website](https://ollama.com/).
Then download the required models (can be replaced in .env):

```bash
# Download language model
ollama run deepseek-r1:1.5b
# Download text embedding model
ollama pull nomic-embed-text
```

Clone the project:

```bash
git clone https://github.com/heyjiacheng/Backend_Red_Panda.git
cd Backend_Red_Panda
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the backend server:

```bash
python3 app.py
```

## API Documentation

### Knowledge Base Management

#### Create Knowledge Base

```bash
curl -X POST http://localhost:8080/knowledge-bases -H "Content-Type: application/json" -d '{"name": "research_paper", "description": "my_papers"}'
```

#### List All Knowledge Bases

```bash
curl -X GET http://localhost:8080/knowledge-bases
```

#### Get Knowledge Base Details

```bash
curl -X GET http://localhost:8080/knowledge-bases/1
```

#### Update Knowledge Base

```bash
curl -X PUT http://localhost:8080/knowledge-bases/1 -H "Content-Type: application/json" -d '{"name": "updated_name", "description": "updated_description"}'
```

#### Delete Knowledge Base

```bash
curl -X DELETE http://localhost:8080/knowledge-bases/1
```

### Document Processing

#### Upload Document

```bash
# Upload to a specific knowledge base (knowledge base #2)
curl -X POST http://localhost:8080/upload/2 -F file=@/Users/jiadengxu/Documents/3d_gaussian_splatting_low.pdf
```

#### List All Documents

```bash
# List all documents
curl -X GET http://localhost:8080/documents

# List documents from a specific knowledge base (e.g., knowledge base #2)
curl -X GET "http://localhost:8080/documents?knowledge_base_id=2"
```

#### Get Document Details

```bash
curl -X GET http://localhost:8080/documents/1
```

#### Download Document

```bash
curl -X GET http://localhost:8080/documents/1/download --output downloaded_document.pdf
```

#### Delete Document

```bash
curl -X DELETE http://localhost:8080/documents/1
```

### Conversation History Management

#### Create New Conversation

```bash
# Create a new conversation (not associated with any knowledge base)
curl -X POST http://localhost:8080/conversations -H "Content-Type: application/json" -d '{"title": "My First Conversation"}'

# Create a new conversation (associated with a specific knowledge base)
curl -X POST http://localhost:8080/conversations -H "Content-Type: application/json" -d '{"title": "Discussion about Research Paper", "knowledge_base_id": 2}'
```

#### Get Conversation List

```bash
# Get all conversations
curl -X GET http://localhost:8080/conversations

# Get conversations for a specific knowledge base (e.g., knowledge base #2)
curl -X GET "http://localhost:8080/conversations?knowledge_base_id=2"

# Paginate conversation list
curl -X GET "http://localhost:8080/conversations?limit=10&offset=0"
```

#### Get Conversation Details

```bash
curl -X GET http://localhost:8080/conversations/1
```

#### Delete Conversation

```bash
curl -X DELETE http://localhost:8080/conversations/1
```

#### Manually Add Message to Conversation

```bash
# Add user message
curl -X POST http://localhost:8080/conversations/1/messages -H "Content-Type: application/json" -d '{"message_type": "user", "content": "What are the main points of this paper?"}'

# Add assistant message
curl -X POST http://localhost:8080/conversations/1/messages -H "Content-Type: application/json" -d '{"message_type": "assistant", "content": "This paper mainly discusses..."}'
```

### Query Functionality

#### Ask Questions

```bash
# Query across all knowledge bases (without saving conversation history)
curl -X POST http://localhost:8080/query -H "Content-Type: application/json" -d '{"query": "What technique used here for 3D scene reconstruction?"}'

# Query in a specific knowledge base (without saving conversation history)
curl -X POST http://localhost:8080/query -H "Content-Type: application/json" -d '{"query": "What 3D reconstruction techniques are used in this research?", "knowledge_base_id": 2}'

# Query in a specific knowledge base (and save to conversation history)
curl -X POST http://localhost:8080/query -H "Content-Type: application/json" -d '{"query": "What are the main innovations in this paper?", "knowledge_base_id": 2, "conversation_id": 1}'
```

### Health Check

```bash
# System health check
curl http://localhost:8080/health
```
