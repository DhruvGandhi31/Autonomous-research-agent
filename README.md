# Research Agent Backend - Setup Instructions

## Quick Start (Recommended)

### Step 1: Create the Project Structure
```bash
# Create main directory
mkdir research-agent && cd research-agent

# Create backend structure
mkdir -p backend/{app/{config,core,tools,services,models,api/routes,api/middleware,utils,data/{vectorstore,documents,reports,cache,memory}},tests,scripts}

# Navigate to backend
cd backend
```

### Step 2: Create All Files

Create these files in your `backend/` directory:

1. **Requirements file**: Save the updated `requirements.txt`
2. **Configuration**: 
   - `app/config/__init__.py` (empty file)
   - `app/config/settings.py` (from settings guide)
3. **Core files**:
   - `app/core/__init__.py` (empty file)
   - `app/core/memory.py` (Memory Manager)
   - `app/core/planner.py` (Task Planner)  
   - `app/core/agent.py` (Updated Agent)
4. **Services**:
   - `app/services/__init__.py` (empty file)
   - `app/services/llm_service.py` (from guide above)
   - `app/services/vector_service.py` (from guide above)
5. **Tools**:
   - `app/tools/__init__.py` (empty file)
   - `app/tools/base_tool.py` (from web crawler code)
   - `app/tools/web_search.py` (Web Search Tool)
   - `app/tools/summarizer.py` (Summarizer Tool)
6. **API**:
   - `app/api/__init__.py` (empty file)
   - `app/api/routes/__init__.py` (empty file)  
   - `app/api/routes/research.py` (API Routes)
7. **Main app**: `app/main.py` (Complete FastAPI Main Application)
8. **Scripts**: `scripts/start_and_test.sh` (Startup script)
9. **Test client**: `test_client.py` (Python Test Client)

### Step 3: Run the Setup Script
```bash
# Make script executable
chmod +x scripts/start_and_test.sh

# Run setup and testing
./scripts/start_and_test.sh
```

## Manual Setup (Alternative)

If you prefer to set up manually:

### 1. Install Dependencies
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 2. Setup Ollama
```bash
# Install Ollama (if not already installed)
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama service
ollama serve

# Pull required models (in another terminal)
ollama pull llama3.1:8b
ollama pull nomic-embed-text
```

### 3. Setup Environment
```bash
# Create .env file
cp .env.example .env

# Create necessary directories
mkdir -p app/data/{vectorstore,documents,reports,cache,memory}
mkdir -p logs
```

### 4. Start the Server
```bash
cd backend/app
python main.py
```

## Testing the API

### Option 1: Using the Test Client
```bash
# Run the interactive test client
python test_client.py
```

### Option 2: Using curl commands

#### Health Check
```bash
curl http://localhost:8000/health
```

#### Test LLM Connection
```bash
curl http://localhost:8000/api/research/test/llm
```

#### Test Web Search
```bash
curl -X POST "http://localhost:8000/api/research/test/search?query=artificial%20intelligence&max_results=3"
```

#### Start Research
```bash
curl -X POST "http://localhost:8000/api/research/start" \
  -H "Content-Type: application/json" \
  -d '{"topic": "quantum computing", "max_sources": 5}'
```

#### Check Research Status
```bash
# Replace RESEARCH_ID with actual ID from start response
curl "http://localhost:8000/api/research/status/RESEARCH_ID"
```

#### Get Research Results
```bash
curl "http://localhost:8000/api/research/results/RESEARCH_ID"
```

### Option 3: Using FastAPI Docs
Navigate to http://localhost:8000/docs for interactive API documentation.

## API Endpoints Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Root endpoint with API info |
| GET | `/health` | Health check |
| GET | `/docs` | Interactive API documentation |
| POST | `/api/research/start` | Start new research |
| GET | `/api/research/status/{research_id}` | Get research status |
| GET | `/api/research/results/{research_id}` | Get research results |
| DELETE | `/api/research/session/{research_id}` | Delete research session |
| GET | `/api/research/sessions` | List all sessions |
| POST | `/api/research/test/search` | Test web search |
| POST | `/api/research/test/summarize` | Test summarization |
| GET | `/api/research/test/llm` | Test LLM connection |

## Example Research Flow

1. **Start Research**:
   ```json
   POST /api/research/start
   {
     "topic": "machine learning in healthcare",
     "max_sources": 10,
     "include_analysis": true
   }
   ```

2. **Monitor Progress**:
   ```bash
   GET /api/research/status/{research_id}
   ```

3. **Get Results**:
   ```bash
   GET /api/research/results/{research_id}
   ```

## Troubleshooting

### Common Issues

1. **"Ollama service unavailable"**
   - Make sure Ollama is running: `ollama serve`
   - Check if models are pulled: `ollama list`

2. **"ModuleNotFoundError"**
   - Make sure virtual environment is activated
   - Install requirements: `pip install -r requirements.txt`

3. **"Port already in use"**
   - Change port in `.env` file: `API_PORT=8001`
   - Or kill existing process: `lsof -ti:8000 | xargs kill`

4. **Search not working**
   - Check internet connection
   - Some websites may block automated requests

### Logs
Check logs for detailed error information:
- Console logs: Real-time output
- File logs: `logs/research_agent.log`

## Next Steps

Once the basic backend is working:

1. **Add more tools**: PDF parser, academic paper search, etc.
2. **Improve analysis**: Better synthesis and insights
3. **Add visualization**: Charts and graphs for data
4. **Build frontend**: Next.js interface
5. **Add authentication**: User management and API keys
6. **Scale up**: Docker deployment, load balancing

## File Structure Reference
```
backend/
├── app/
│   ├── main.py                    # FastAPI application
│   ├── config/
│   │   └── settings.py           # Configuration management
│   ├── core/
│   │   ├── agent.py              # Main research agent
│   │   ├── memory.py             # Memory management
│   │   └── planner.py            # Task planning
│   ├── services/
│   │   ├── llm_service.py        # Ollama integration
│   │   └── vector_service.py     # ChromaDB integration
│   ├── tools/
│   │   ├── base_tool.py          # Tool interface
│   │   ├── web_search.py         # DuckDuckGo search
│   │   └── summarizer.py         # Text summarization
│   ├── api/routes/
│   │   └── research.py           # Research endpoints
│   └── data/                     # Data storage
├── scripts/
│   └── start_and_test.sh         # Setup script
├── test_client.py                # Test client
├── requirements.txt              # Dependencies
└── .env                          # Environment variables
```

Happy researching! 🔬✨