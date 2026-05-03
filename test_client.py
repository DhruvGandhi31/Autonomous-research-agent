# backend/test_client.py
import requests
import json
import time
from typing import Dict, Any

class ResearchAgentClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
    
    def health_check(self) -> Dict[str, Any]:
        """Check if the API is healthy"""
        try:
            response = self.session.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    def test_llm(self) -> Dict[str, Any]:
        """Test LLM connection"""
        try:
            response = self.session.get(f"{self.base_url}/api/research/test/llm")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    def test_search(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """Test web search"""
        try:
            params = {"query": query, "max_results": max_results}
            response = self.session.post(f"{self.base_url}/api/research/test/search", params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    def test_summarize(self, content: str, topic: str = "general") -> Dict[str, Any]:
        """Test summarization"""
        try:
            params = {"content": content, "topic": topic}
            response = self.session.post(f"{self.base_url}/api/research/test/summarize", params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    def start_research(self, topic: str, max_sources: int = 10) -> Dict[str, Any]:
        """Start a research session"""
        try:
            data = {
                "topic": topic,
                "requirements": {"max_sources": max_sources},
                "include_analysis": True
            }
            response = self.session.post(
                f"{self.base_url}/api/research/start", 
                json=data
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    def get_research_status(self, research_id: str) -> Dict[str, Any]:
        """Get research status"""
        try:
            response = self.session.get(f"{self.base_url}/api/research/status/{research_id}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    def get_research_results(self, research_id: str) -> Dict[str, Any]:
        """Get complete research results"""
        try:
            response = self.session.get(f"{self.base_url}/api/research/results/{research_id}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    def wait_for_research_completion(self, research_id: str, max_wait: int = 300) -> Dict[str, Any]:
        """Wait for research to complete and return results"""
        print(f"⏳ Waiting for research {research_id} to complete...")
        
        start_time = time.time()
        while time.time() - start_time < max_wait:
            status = self.get_research_status(research_id)
            
            if "error" in status:
                return status
            
            current_status = status.get("status", "unknown")
            progress = status.get("progress", 0)
            current_task = status.get("current_task", "")
            
            print(f"📊 Status: {current_status} | Progress: {progress:.1f}% | Task: {current_task}")
            
            if current_status in ["completed", "error"]:
                break
            
            time.sleep(5)
        
        # Get final results
        return self.get_research_results(research_id)

def main():
    """Demo the research agent capabilities"""
    client = ResearchAgentClient()
    
    print("🔬 Research Agent Demo")
    print("=" * 50)
    
    # 1. Health check
    print("\n1. 🏥 Health Check")
    health = client.health_check()
    print(f"Status: {health.get('status', 'unknown')}")
    if health.get("services", {}).get("ollama") != "available":
        print("❌ Ollama is not available. Please start Ollama and try again.")
        return
    
    # 2. Test LLM
    print("\n2. 🤖 Testing LLM Connection")
    llm_test = client.test_llm()
    if "error" not in llm_test:
        print(f"✅ LLM Response: {llm_test.get('response', '')[:100]}...")
    else:
        print(f"❌ LLM Test Failed: {llm_test['error']}")
        return
    
    # 3. Test Web Search
    print("\n3. 🔍 Testing Web Search")
    search_test = client.test_search("artificial intelligence trends 2024", max_results=3)
    if "error" not in search_test:
        results = search_test.get("results", [])
        print(f"✅ Found {len(results)} search results")
        for i, result in enumerate(results[:2]):
            print(f"   {i+1}. {result.get('title', 'No title')}")
    else:
        print(f"❌ Search Test Failed: {search_test['error']}")
    
    # 4. Test Summarization
    print("\n4. 📝 Testing Summarization")
    sample_text = """
    Artificial Intelligence (AI) is rapidly transforming industries across the globe. 
    Machine learning, a subset of AI, enables computers to learn from data without explicit programming. 
    Recent advances in deep learning have led to breakthroughs in natural language processing, 
    computer vision, and autonomous systems. However, challenges remain in ensuring AI safety, 
    addressing bias, and maintaining human oversight in critical applications.
    """
    
    summary_test = client.test_summarize(sample_text, "artificial intelligence")
    if "error" not in summary_test:
        summary = summary_test.get("structured", {}).get("executive_summary", "")
        print(f"✅ Summary: {summary[:150]}...")
    else:
        print(f"❌ Summarization Test Failed: {summary_test['error']}")
    
    # 5. Full Research Demo
    print("\n5. 🔬 Full Research Demo")
    research_topic = input("Enter a research topic (or press Enter for 'quantum computing basics'): ").strip()
    if not research_topic:
        research_topic = "quantum computing basics"
    
    print(f"🚀 Starting research on: '{research_topic}'")
    
    # Start research
    research_response = client.start_research(research_topic, max_sources=5)
    if "error" in research_response:
        print(f"❌ Failed to start research: {research_response['error']}")
        return
    
    research_id = research_response.get("research_id")
    print(f"📋 Research ID: {research_id}")
    
    # Wait for completion
    results = client.wait_for_research_completion(research_id)
    
    if "error" not in results:
        print("\n🎉 Research Complete!")
        print("-" * 30)
        
        context = results.get("context", {})
        task_results = results.get("task_results", [])
        
        print(f"📊 Topic: {context.get('topic', 'Unknown')}")
        print(f"📅 Started: {context.get('started_at', 'Unknown')}")
        print(f"✅ Status: {context.get('status', 'Unknown')}")
        print(f"🔍 Tasks Completed: {len(task_results)}")
        
        # Show sources found
        total_sources = sum(len(task.get("sources", [])) for task in task_results)
        print(f"📚 Total Sources Found: {total_sources}")
        
        # Show some sample sources
        if task_results and task_results[0].get("sources"):
            print("\n📖 Sample Sources:")
            for i, source in enumerate(task_results[0]["sources"][:3]):
                print(f"   {i+1}. {source.get('title', 'No title')}")
                print(f"      {source.get('url', 'No URL')}")
        
        # Show summaries if available
        if task_results:
            for task in task_results:
                if task.get("synthesis"):
                    print(f"\n💡 Research Analysis:")
                    print(task["synthesis"][:300] + "...")
                    break
        
        print(f"\n🔗 Full results available at: /api/research/results/{research_id}")
    else:
        print(f"❌ Research failed: {results['error']}")

if __name__ == "__main__":
    main()