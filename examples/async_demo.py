#!/usr/bin/env python3
"""
Example demonstrating async page handlers and validators.

This example shows:
1. Registering both sync and async page handlers
2. Using async validators for validation logic that requires I/O
3. Bulk page retrieval with async execution for better performance
4. Mixed sync/async execution patterns
"""

import asyncio
import time
from typing import Any

# Note: This is a demo script that would work once dependencies are available
# For now it serves as documentation of the async API

# Simulated imports - these would work with full dependencies
class MockServerContext:
    def __init__(self, root: str): pass
    def route(self, path: str): pass
    def validator(self, func): pass
    async def get_page_async(self, uri): pass
    async def get_pages_async(self, uris): pass

class MockPage:
    def __init__(self, **data): pass

class MockPageURI:
    def __init__(self, **data): pass

# In real usage, these would be:
# from praga_core import ServerContext
# from praga_core.types import Page, PageURI

ServerContext = MockServerContext
Page = MockPage  
PageURI = MockPageURI


class EmailPage(Page):
    """Example email page."""
    subject: str
    sender: str
    content: str
    verified: bool = False


class DocumentPage(Page):
    """Example document page."""
    title: str
    content: str
    word_count: int


async def main():
    """Demonstrate async functionality."""
    print("=== Async Page Handler Demo ===\\n")
    
    # Create context
    context = ServerContext(root="example")

    # === 1. Register sync handler (existing pattern) ===
    @context.route("documents")
    def handle_documents(uri: PageURI) -> DocumentPage:
        """Sync document handler."""
        print(f"📄 Processing document {uri.id} (sync)")
        return DocumentPage(
            uri=uri,
            title=f"Document {uri.id}",
            content=f"Content for document {uri.id}",
            word_count=len(f"Content for document {uri.id}".split())
        )

    # === 2. Register async handler (new capability) ===
    @context.route("emails")  
    async def handle_emails(uri: PageURI) -> EmailPage:
        """Async email handler that fetches data from API."""
        print(f"📧 Fetching email {uri.id} (async)")
        
        # Simulate async API call
        await asyncio.sleep(0.1)
        email_data = await fetch_email_from_api(uri.id)
        
        return EmailPage(
            uri=uri,
            subject=email_data["subject"],
            sender=email_data["sender"], 
            content=email_data["content"],
            verified=email_data["verified"]
        )

    # === 3. Register async validator ===
    @context.validator
    async def validate_email(page: EmailPage) -> bool:
        """Async email validator that checks sender reputation."""
        print(f"🔍 Validating email from {page.sender} (async)")
        
        # Simulate async validation (e.g., checking reputation API)
        await asyncio.sleep(0.05)
        is_trusted = await check_sender_reputation(page.sender)
        
        return is_trusted and page.verified

    # === 4. Single page retrieval ===
    print("1. Single page retrieval:")
    
    # Sync handler via async method
    doc_uri = PageURI(root="example", type="documents", id="report1", version=1)
    doc_page = await context.get_page_async(doc_uri)
    print(f"   Retrieved: {doc_page.title}")
    
    # Async handler
    email_uri = PageURI(root="example", type="emails", id="msg123", version=1)  
    email_page = await context.get_page_async(email_uri)
    print(f"   Retrieved: {email_page.subject}")
    print()

    # === 5. Bulk page retrieval ===
    print("2. Bulk page retrieval (demonstrates parallelism):")
    
    uris = [
        PageURI(root="example", type="emails", id="msg1", version=1),
        PageURI(root="example", type="emails", id="msg2", version=1),
        PageURI(root="example", type="emails", id="msg3", version=1),
        PageURI(root="example", type="documents", id="doc1", version=1),
        PageURI(root="example", type="documents", id="doc2", version=1),
    ]
    
    start_time = time.time()
    pages = await context.get_pages_async(uris)
    end_time = time.time()
    
    print(f"   Retrieved {len(pages)} pages in {end_time - start_time:.3f}s")
    print(f"   (Parallel execution - would be ~0.5s if sequential)")
    print()

    # === 6. Benefits summary ===
    print("3. Benefits of async architecture:")
    print("   ✅ Parallel execution of I/O-bound operations")
    print("   ✅ Better resource utilization") 
    print("   ✅ Backward compatibility with sync handlers")
    print("   ✅ Async validators for complex validation logic")
    print("   ✅ Bulk operations for improved performance")


async def fetch_email_from_api(email_id: str) -> dict:
    """Simulate fetching email data from an API."""
    # In real usage, this would be an actual API call
    return {
        "subject": f"Email Subject {email_id}",
        "sender": f"user{email_id}@example.com",
        "content": f"This is the content of email {email_id}",
        "verified": True
    }


async def check_sender_reputation(sender: str) -> bool:
    """Simulate checking sender reputation via API."""
    # In real usage, this would check against a reputation service
    return not sender.startswith("spam")


if __name__ == "__main__":
    # Note: This demo would run with full dependencies
    print("This is a demo script showing the async API.")
    print("With full dependencies, you would run: asyncio.run(main())")
    print()
    print("Key async features implemented:")
    print("- async def page_handlers") 
    print("- async def validators")
    print("- await context.get_page_async(uri)")
    print("- await context.get_pages_async(uris)")
    print("- Automatic sync/async handler detection")
    print("- Thread pool execution for sync handlers in async context")