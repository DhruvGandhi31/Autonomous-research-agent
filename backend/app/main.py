# backend/app/main.py
from datetime import datetime
from contextlib import asynccontextmanager
import sys
import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Add the app directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.settings import settings
from core.agent import research_agent
from tools.web_search import web_search_tool
from tools.summarizer import summarizer_tool
from tools.academic_search import academic_search_tool
from services.llm_service import llm_service
from api.routes.research import router as research_router
from loguru import logger

# Configure logging
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)
logger.add(
    "logs/research_agent.log",
    rotation="1 day",
    retention="7 days",
    level="DEBUG"
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    # Startup
    logger.info("🚀 Starting Research Agent Backend")
    
    # Create necessary directories
    data_dir = Path("./app/data")
    for subdir in ["vectorstore", "documents", "reports", "cache", "memory"]:
        (data_dir / subdir).mkdir(parents=True, exist_ok=True)
    
    # Create logs directory
    Path("logs").mkdir(exist_ok=True)
    
    # Check Ollama connection
    logger.info("🔍 Checking Ollama connection...")
    if not llm_service.is_available():
        logger.error("❌ Ollama service is not available! Make sure Ollama is running.")
        logger.error("💡 Run: ollama serve")
        raise RuntimeError("Ollama service required")
    
    logger.info("✅ Ollama connection successful")
    
    # Register tools with agent
    logger.info("🔧 Registering tools...")
    research_agent.register_tool("web_search", web_search_tool)
    research_agent.register_tool("summarizer", summarizer_tool)
    research_agent.register_tool("academic_search", academic_search_tool)
    
    logger.info("✅ Backend startup complete")
    logger.info(f"🌐 API running at http://{settings.api_host}:{settings.api_port}")
    logger.info("📚 Available endpoints:")
    logger.info("   - GET  /              - Root endpoint")
    logger.info("   - GET  /health        - Health check")
    logger.info("   - POST /api/research/start - Start research")
    logger.info("   - GET  /api/research/status/{research_id} - Get status")
    logger.info("   - GET  /api/research/results/{research_id} - Get results")
    logger.info("   - POST /api/research/test/search - Test web search")
    logger.info("   - POST /api/research/test/summarize - Test summarization")
    logger.info("   - GET  /api/research/test/llm - Test LLM connection")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down Research Agent Backend")
    
    # Close tool sessions
    await web_search_tool.close()
    await summarizer_tool.close()
    await academic_search_tool.close()

app = FastAPI(
    title="Research Agent API",
    description="Autonomous Research Agent Backend - Build powerful research reports automatically",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # Next.js frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(research_router, prefix="/api/research", tags=["research"])

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "🔬 Research Agent API",
        "status": "running",
        "version": "1.0.0",
        "description": "Autonomous research agent for comprehensive topic analysis",
        "docs": "/docs",
        "health_check": "/health"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        ollama_status = llm_service.is_available()
        
        return {
            "status": "healthy" if ollama_status else "degraded",
            "timestamp": datetime.now().isoformat(),
            "services": {
                "ollama": "available" if ollama_status else "unavailable",
                "agent": research_agent.state.value,
                "model": llm_service.model
            },
            "active_sessions": len(research_agent.memory.active_sessions)
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

if __name__ == "__main__":
    logger.info("🎯 Starting Research Agent in development mode")
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level="info"
    )