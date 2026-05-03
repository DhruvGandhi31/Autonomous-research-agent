#!/bin/bash
# scripts/start_and_test.sh

set -e

echo "🚀 Research Agent Backend - Startup & Test Script"
echo "=================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if we're in the project root directory
if [ ! -f "requirements.txt" ]; then
    echo -e "${RED}❌ Please run this script from the project root directory${NC}"
    exit 1
fi

echo -e "${BLUE}📦 Step 1: Setting up Python environment...${NC}"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install requirements
echo "Installing requirements..."
pip install --upgrade pip
pip install -r requirements.txt

echo -e "${GREEN}✅ Python environment ready${NC}"

echo -e "${BLUE}🔍 Step 2: Checking Ollama...${NC}"

# Check if Ollama is running
if ! pgrep -x "ollama" > /dev/null; then
    echo -e "${YELLOW}⚠️  Ollama is not running. Starting Ollama...${NC}"
    ollama serve &
    sleep 5
fi

# Check if model is available
if ! ollama list | grep -q "llama3.1:8b"; then
    echo -e "${YELLOW}📥 Pulling llama3.1:8b model...${NC}"
    ollama pull llama3.1:8b
fi

# Pull embedding model if not present
if ! ollama list | grep -q "nomic-embed-text"; then
    echo -e "${YELLOW}📥 Pulling nomic-embed-text model...${NC}"
    ollama pull nomic-embed-text
fi

echo -e "${GREEN}✅ Ollama setup complete${NC}"

echo -e "${BLUE}🏗️  Step 3: Setting up project structure...${NC}"

# Create necessary directories
mkdir -p backend/app/data/{vectorstore,documents,reports,cache,memory}
mkdir -p backend/logs

# Copy environment file if it doesn't exist
if [ ! -f "backend/.env" ]; then
    if [ -f "backend/.env.example" ]; then
        cp backend/.env.example backend/.env
        echo "📝 Created .env file from .env.example"
    else
        echo "📝 Creating default .env file..."
        cat > backend/.env << EOF
# LLM Configuration
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_MODEL=llama3.1:8b
MAX_TOKENS=4096
TEMPERATURE=0.7

# Vector Database
CHROMA_PERSIST_DIRECTORY=./app/data/vectorstore
COLLECTION_NAME=research_documents

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=True

# Crawling Configuration
MAX_CRAWL_DEPTH=3
CRAWL_DELAY=1
USER_AGENT=ResearchAgent/1.0

# Rate Limiting
MAX_REQUESTS_PER_MINUTE=60
EOF
    fi
fi

echo -e "${GREEN}✅ Project structure ready${NC}"

echo -e "${BLUE}🚀 Step 4: Starting the backend server...${NC}"

# Start the server in the background
cd backend/app
python main.py &
SERVER_PID=$!
cd ../..

# Wait for server to start
echo "Waiting for server to start..."
sleep 8

echo -e "${BLUE}🧪 Step 5: Running tests...${NC}"

# Test health endpoint
echo "Testing health endpoint..."
HEALTH_RESPONSE=$(curl -s http://localhost:8000/health || echo "FAILED")
if [[ $HEALTH_RESPONSE == *"healthy"* ]] || [[ $HEALTH_RESPONSE == *"degraded"* ]]; then
    echo -e "${GREEN}✅ Health check passed${NC}"
else
    echo -e "${RED}❌ Health check failed${NC}"
    echo "Response: $HEALTH_RESPONSE"
fi

# Test LLM connection
echo "Testing LLM connection..."
LLM_RESPONSE=$(curl -s http://localhost:8000/api/research/test/llm || echo "FAILED")
if [[ $LLM_RESPONSE == *"success"* ]]; then
    echo -e "${GREEN}✅ LLM connection test passed${NC}"
else
    echo -e "${RED}❌ LLM connection test failed${NC}"
    echo "Response: $LLM_RESPONSE"
fi

# Test web search
echo "Testing web search..."
SEARCH_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/research/test/search?query=artificial%20intelligence&max_results=3" || echo "FAILED")
if [[ $SEARCH_RESPONSE == *"results"* ]]; then
    echo -e "${GREEN}✅ Web search test passed${NC}"
else
    echo -e "${RED}❌ Web search test failed${NC}"
    echo "Response: $SEARCH_RESPONSE"
fi

# Test full research workflow
echo "Testing full research workflow..."
RESEARCH_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/research/start" \
    -H "Content-Type: application/json" \
    -d '{"topic": "machine learning basics", "max_sources": 3}' || echo "FAILED")

if [[ $RESEARCH_RESPONSE == *"research_id"* ]]; then
    echo -e "${GREEN}✅ Research workflow test passed${NC}"
    
    # Extract research ID and check status
    RESEARCH_ID=$(echo $RESEARCH_RESPONSE | grep -o '"research_id":"[^"]*' | cut -d'"' -f4)
    if [ ! -z "$RESEARCH_ID" ]; then
        echo "Research ID: $RESEARCH_ID"
        echo "Waiting for research to complete..."
        sleep 10
        
        STATUS_RESPONSE=$(curl -s "http://localhost:8000/api/research/status/$RESEARCH_ID" || echo "FAILED")
        echo "Status: $STATUS_RESPONSE"
    fi
else
    echo -e "${RED}❌ Research workflow test failed${NC}"
    echo "Response: $RESEARCH_RESPONSE"
fi

echo -e "${BLUE}📊 Step 6: Summary${NC}"
echo "=================================================="
echo -e "${GREEN}🎉 Research Agent Backend is running!${NC}"
echo ""
echo "🌐 API Endpoints:"
echo "   - Health Check: http://localhost:8000/health"
echo "   - API Documentation: http://localhost:8000/docs"
echo "   - Alternative Docs: http://localhost:8000/redoc"
echo ""
echo "🔧 Test Endpoints:"
echo "   - Test LLM: GET http://localhost:8000/api/research/test/llm"
echo "   - Test Search: POST http://localhost:8000/api/research/test/search"
echo "   - Test Summary: POST http://localhost:8000/api/research/test/summarize"
echo ""
echo "🔬 Research Endpoints:"
echo "   - Start Research: POST http://localhost:8000/api/research/start"
echo "   - Get Status: GET http://localhost:8000/api/research/status/{research_id}"
echo "   - Get Results: GET http://localhost:8000/api/research/results/{research_id}"
echo ""
echo "📝 Example curl command:"
echo 'curl -X POST "http://localhost:8000/api/research/start" \'
echo '  -H "Content-Type: application/json" \'
echo '  -d '"'"'{"topic": "quantum computing", "max_sources": 5}'"'"
echo ""
echo -e "${YELLOW}🛑 To stop the server: kill $SERVER_PID${NC}"
echo -e "${BLUE}📋 Server logs are available in backend/logs/research_agent.log${NC}"
echo ""
echo -e "${GREEN}Happy researching! 🔬✨${NC}"

# Keep the script running so server stays alive
echo "Press Ctrl+C to stop the server..."
wait $SERVER_PID