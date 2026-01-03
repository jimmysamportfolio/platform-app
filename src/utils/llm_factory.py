"""
LLM Factory Module

Helper to initialize and manage LLM client instances.
This module is responsible for:
- Creating LLM client instances with centralized configuration
- Managing API key configuration
- Providing consistent LLM interfaces across the application
- Supporting the new google.genai SDK (replaces deprecated google.generativeai)
"""

import os
import sys

# Add project root to path for config imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

# New google.genai SDK (unified client approach)
from google import genai
from google.genai import types

from config.settings import DEFAULT_LLM_MODEL, DEFAULT_EMBEDDING_MODEL, LLM_TEMPERATURE

load_dotenv()


def get_genai_client(api_key: str = None) -> genai.Client:
    """
    Get a configured Google GenAI Client instance.
    
    This is the new unified client from the google-genai SDK.
    
    Args:
        api_key: API key (defaults to GOOGLE_API_KEY environment variable).
        
    Returns:
        Configured genai.Client instance.
        
    Raises:
        ValueError: If GOOGLE_API_KEY environment variable is not set.
    """
    key = api_key or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise ValueError("GOOGLE_API_KEY environment variable not set")
    
    return genai.Client(api_key=key)


def generate_content(
    prompt: str,
    model: str = None,
    temperature: float = None,
    system_instruction: str = None,
    api_key: str = None,
) -> str:
    """
    Generate content using the new google.genai SDK.
    
    This is a simple wrapper for common use cases.
    
    Args:
        prompt: The prompt/content to send to the model.
        model: Model name (defaults to DEFAULT_LLM_MODEL from settings).
        temperature: Temperature for generation (defaults to LLM_TEMPERATURE).
        system_instruction: Optional system instruction.
        api_key: API key (defaults to GOOGLE_API_KEY environment variable).
        
    Returns:
        Generated text response.
        
    Raises:
        ValueError: If GOOGLE_API_KEY environment variable is not set.
    """
    client = get_genai_client(api_key)
    
    config = types.GenerateContentConfig(
        temperature=temperature if temperature is not None else LLM_TEMPERATURE,
    )
    
    if system_instruction:
        config.system_instruction = system_instruction
    
    response = client.models.generate_content(
        model=model or DEFAULT_LLM_MODEL,
        contents=prompt,
        config=config,
    )
    
    return response.text


def get_chat_llm(
    model: str = None,
    temperature: float = None,
) -> ChatGoogleGenerativeAI:
    """
    Get a configured ChatGoogleGenerativeAI instance (LangChain).
    
    This uses the langchain-google-genai package which wraps the new SDK.
    
    Args:
        model: Model name (defaults to DEFAULT_LLM_MODEL from settings).
        temperature: Temperature for generation (defaults to LLM_TEMPERATURE).
        
    Returns:
        Configured ChatGoogleGenerativeAI instance.
        
    Raises:
        ValueError: If GOOGLE_API_KEY environment variable is not set.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable not set")
    
    return ChatGoogleGenerativeAI(
        model=model or DEFAULT_LLM_MODEL,
        temperature=temperature if temperature is not None else LLM_TEMPERATURE,
        google_api_key=api_key,
    )


def get_embeddings(model: str = None) -> GoogleGenerativeAIEmbeddings:
    """
    Get a configured GoogleGenerativeAIEmbeddings instance.
    
    Args:
        model: Embedding model name (defaults to DEFAULT_EMBEDDING_MODEL).
        
    Returns:
        Configured GoogleGenerativeAIEmbeddings instance.
        
    Raises:
        ValueError: If GOOGLE_API_KEY environment variable is not set.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable not set")
    
    return GoogleGenerativeAIEmbeddings(
        model=model or DEFAULT_EMBEDDING_MODEL,
        google_api_key=api_key,
    )


# --- Test Block ---
if __name__ == "__main__":
    print("Testing LLM Factory...")
    
    # Test new genai client
    try:
        client = get_genai_client()
        print(f"✅ GenAI Client created")
    except Exception as e:
        print(f"❌ GenAI Client error: {e}")
    
    # Test generate_content
    try:
        result = generate_content("Say 'Hello' in 3 words or less")
        print(f"✅ Generate content: {result[:50]}...")
    except Exception as e:
        print(f"❌ Generate content error: {e}")
    
    # Test chat LLM (LangChain)
    try:
        llm = get_chat_llm()
        print(f"✅ Chat LLM created: {DEFAULT_LLM_MODEL}")
    except Exception as e:
        print(f"❌ Chat LLM error: {e}")
    
    # Test embeddings
    try:
        embeddings = get_embeddings()
        print(f"✅ Embeddings created: {DEFAULT_EMBEDDING_MODEL}")
    except Exception as e:
        print(f"❌ Embeddings error: {e}")
    
    print("\n✅ LLM Factory tests complete!")
