from app.llm.ollama_client import OllamaJSONClient
from app.schemas.slides import PresentationOutlineResponse

def test_outline_generation():
    client = OllamaJSONClient()
    
    prompt = """
    Create a presentation outline based on the following:
    - Topic: Introduction to Artificial Intelligence and RAG Systems
    - Slide Count: 3
    - Target Audience: Computer Science Students
    - Style: Professional & Educational
    - Context: RAG (Retrieval-Augmented Generation) combines LLMs with external knowledge bases.
    """
    
    try:
        result = client.generate_json(prompt, PresentationOutlineResponse)
        print("Success! Generated Outline:")
        print(result.model_dump_json(indent=2))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_outline_generation()